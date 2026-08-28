"""初始化插件"""

from nonebot import get_loaded_plugins
from nonebot.plugin import Plugin, PluginMetadata

from liuying.configs.utils import PluginExtraData, PluginSetting
from liuying.models.plugin_info import PluginInfo
from liuying.models.plugin_limit import PluginLimit
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.manager.priority_manager import PriorityLifecycle

from .manager import manager


def _parse_metadata(plugin: Plugin) -> PluginExtraData | None:
    """解析插件元数据

    参数:
        plugin: Plugin 实例

    返回:
        PluginExtraData 或 None（无元数据且无子插件时跳过注册）
    """
    metadata = plugin.metadata
    if not metadata:
        if not plugin.sub_plugins:
            return None
        metadata = PluginMetadata(name=plugin.name, description="", usage="")

    extra_data = PluginExtraData(**metadata.extra)

    if metadata.type == "library":
        extra_data.plugin_type = PluginType.HIDDEN

    if extra_data.plugin_type == PluginType.HIDDEN:
        extra_data.menu_type = ""

    if plugin.sub_plugins:
        extra_data.plugin_type = PluginType.PARENT

    return extra_data


async def _handle_setting(
    plugin: Plugin,
    plugin_list: list[PluginInfo],
    limit_list: list[PluginLimit],
) -> None:
    """处理插件设置

    参数:
        plugin: Plugin 实例
        plugin_list: 插件列表
        limit_list: 插件限制列表
    """
    extra_data = _parse_metadata(plugin)
    if not extra_data:
        return

    logger.debug(
        f"{extra_data.plugin_type}:{plugin.name} -> 注册插件",
        "初始化插件数据",
    )

    setting = extra_data.setting or PluginSetting()

    plugin_list.append(
        PluginInfo(
            module=plugin.name,
            module_path=plugin.module_name,
            name=plugin.metadata.name if plugin.metadata else plugin.name,
            author=extra_data.author,
            version=extra_data.version,
            level=setting.level,
            default_status=setting.default_status,
            limit_superuser=setting.limit_superuser,
            menu_type=extra_data.menu_type,
            cost_gold=setting.cost_gold,
            plugin_type=extra_data.plugin_type,
            admin_level=extra_data.admin_level,
            is_show=extra_data.is_show,
            ignore_prompt=extra_data.ignore_prompt,
            parent=(plugin.parent_plugin.module_name if plugin.parent_plugin else None),
        )
    )

    if extra_data.limits:
        limit_list.extend(
            PluginLimit(
                module=plugin.name,
                module_path=plugin.module_name,
                limit_type=limit._type,
                watch_type=limit.watch_type,
                status=limit.status,
                check_type=limit.check_type,
                result=limit.result,
                cd=getattr(limit, "cd", None),
                max_count=getattr(limit, "max_count", None),
            )
            for limit in extra_data.limits
        )


@PriorityLifecycle.on_startup(priority=5)
async def _() -> None:
    """初始化插件数据配置"""
    plugin_list: list[PluginInfo] = []
    limit_list: list[PluginLimit] = []
    load_plugin: list[str] = []

    existing_plugins = await PluginInfo.filter().all()
    module2plugin = {p.module_path: p for p in existing_plugins}

    for plugin in get_loaded_plugins():
        load_plugin.append(plugin.module_name)
        await _handle_setting(plugin, plugin_list, limit_list)

    create_list: list[PluginInfo] = []
    update_list: list[PluginInfo] = []

    for plugin in plugin_list:
        if plugin.module_path not in module2plugin:
            create_list.append(plugin)
        else:
            db_plugin = module2plugin[plugin.module_path]
            db_plugin.name = plugin.name
            db_plugin.author = plugin.author
            db_plugin.version = plugin.version
            db_plugin.admin_level = plugin.admin_level
            db_plugin.plugin_type = plugin.plugin_type
            db_plugin.is_show = plugin.is_show
            update_list.append(db_plugin)

    if create_list:
        await PluginInfo.filter().bulk_create(create_list)

    if update_list:
        await PluginInfo.filter().bulk_update(
            update_list,
            ["name", "author", "version", "admin_level", "plugin_type", "is_show"],
        )

    # 维护加载状态：已加载模块置 True，其余置 False
    await PluginInfo.filter(PluginInfo.module_path.in_(load_plugin)).update(
        load_status=True
    )
    await PluginInfo.filter(~PluginInfo.module_path.in_(load_plugin)).update(
        load_status=False
    )

    manager.init()
    for limit in limit_list:
        if not manager.exists(limit.module, limit.limit_type):
            manager.add(limit.module, limit)
    manager.save_file()
    await manager.load_to_db()

    logger.info(
        f"插件数据初始化完成: 新增 {len(create_list)} 个, 更新 {len(update_list)} 个",
        "初始化插件数据",
    )
