"""初始化插件"""

import nonebot
from nonebot import get_loaded_plugins
from nonebot.drivers import Driver
from nonebot.plugin import Plugin, PluginMetadata
import orjson as json
from ruamel.yaml import YAML

from liuying.configs.path_config import DATA_PATH
from liuying.configs.utils import PluginExtraData, PluginSetting
from liuying.models._group import GroupConsole
from liuying.models.plugin_info import PluginInfo
from liuying.models.plugin_limit import PluginLimit
from liuying.models.task_info import TaskInfo
from liuying.utils.enum import (
    BlockType,
    LimitCheckType,
    LimitWatchType,
    PluginType,
)
from liuying.utils.log import logger
from liuying.utils.manager.priority_manager import PriorityLifecycle

from .manager import manager

_yaml = YAML(pure=True)
_yaml.allow_unicode = True
_yaml.indent = 2

driver: Driver = nonebot.get_driver()


def _parse_limit_check_type(check_type_str: str | None) -> LimitCheckType:
    """解析限制检查类型

    参数:
        check_type_str: 检查类型字符串

    返回:
        LimitCheckType 枚举值
    """
    match check_type_str:
        case "private":
            return LimitCheckType.PRIVATE
        case "group":
            return LimitCheckType.GROUP
        case _:
            return LimitCheckType.ALL


def _parse_limit_watch_type(watch_type_str: str | None) -> LimitWatchType:
    """解析限制监听类型

    参数:
        watch_type_str: 监听类型字符串

    返回:
        LimitWatchType 枚举值
    """
    return LimitWatchType.GROUP if watch_type_str == "group" else LimitWatchType.USER


def _parse_block_type(block_type_str: str | None) -> BlockType | None:
    """解析阻塞类型

    参数:
        block_type_str: 阻塞类型字符串

    返回:
        BlockType 枚举值或 None
    """
    match block_type_str:
        case "all":
            return BlockType.ALL
        case "private":
            return BlockType.PRIVATE
        case "group":
            return BlockType.GROUP
        case _:
            return None


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
    metadata = plugin.metadata
    if not metadata:
        if not plugin.sub_plugins:
            return
        metadata = PluginMetadata(name=plugin.name, description="", usage="")

    extra = metadata.extra
    extra_data = PluginExtraData(**extra)
    logger.debug(f"{metadata.name}:{plugin.name} -> {extra}", "初始化插件数据")

    setting = extra_data.setting or PluginSetting()

    if metadata.type == "library":
        extra_data.plugin_type = PluginType.HIDDEN

    if extra_data.plugin_type == PluginType.HIDDEN:
        extra_data.menu_type = ""

    if plugin.sub_plugins:
        extra_data.plugin_type = PluginType.PARENT

    plugin_list.append(
        PluginInfo(
            module=plugin.name,
            module_path=plugin.module_name,
            name=metadata.name,
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
            impression=setting.impression,
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
    load_plugin = []

    existing_plugins = await PluginInfo.filter().all()
    module2id = {plugin.module_path: plugin.id for plugin in existing_plugins}

    for plugin in get_loaded_plugins():
        load_plugin.append(plugin.module_name)
        await _handle_setting(plugin, plugin_list, limit_list)

    create_list = []
    update_list = []

    for plugin in plugin_list:
        if plugin.module_path not in module2id:
            create_list.append(plugin)
        else:
            plugin.id = module2id[plugin.module_path]
            update_list.append(plugin)

    if create_list:
        await PluginInfo.filter().bulk_create(create_list)

    if update_list:
        for plugin in update_list:
            if db_plugin := await PluginInfo.filter(id=plugin.id).first():
                db_plugin.name = plugin.name
                db_plugin.author = plugin.author
                db_plugin.version = plugin.version
                db_plugin.admin_level = plugin.admin_level
                db_plugin.plugin_type = plugin.plugin_type
                db_plugin.is_show = plugin.is_show
                await db_plugin.save()

    await data_migration()

    for module_path in load_plugin:
        if plugin := await PluginInfo.filter(module_path=module_path).first():
            plugin.load_status = True
            await plugin.save()

    unloaded_plugins = await PluginInfo.filter(
        ~PluginInfo.module_path.in_(load_plugin)
    ).all()
    for plugin in unloaded_plugins:
        plugin.load_status = False
        await plugin.save()

    manager.init()
    if limit_list:
        for limit in limit_list:
            if not manager.exists(limit.module, limit.limit_type):
                manager.add(limit.module, limit)
    manager.save_file()
    await manager.load_to_db()


async def data_migration() -> None:
    """执行数据迁移"""
    await plugin_migration()
    await group_migration()


async def plugin_migration() -> None:
    """迁移插件数据"""
    setting_file = DATA_PATH / "configs" / "plugins2settings.yaml"
    plugin_file = DATA_PATH / "manager" / "plugins_manager.json"

    if setting_file.exists():
        await _migrate_plugin_settings(setting_file)
        setting_file.unlink()
        logger.info("迁移插件setting数据完成!")

    if plugin_file.exists():
        await _migrate_plugin_manager(plugin_file)
        plugin_file.unlink()
        logger.info("迁移插件数据完成!")


async def _migrate_plugin_settings(setting_file) -> None:
    """迁移插件设置数据

    参数:
        setting_file: 设置文件路径
    """
    import aiofiles

    async with aiofiles.open(setting_file, encoding="utf8") as f:
        if not (data := _yaml.load(await f.read())):
            return

        logger.info("开始迁移插件setting数据...")
        data = data["PluginSettings"]

        plugins = await PluginInfo.filter().where_in("module", list(data.keys())).all()

        for plugin in plugins:
            if plugin_data := data.get(plugin.module):
                plugin.default_status = plugin_data.get("default_status", True)
                plugin.level = plugin_data.get("level", 5)
                plugin.limit_superuser = plugin_data.get("limit_superuser", False)
                plugin.menu_type = plugin_data.get("plugin_type", ["功能"])[0]
                plugin.cost_gold = plugin_data.get("cost_gold", 0)
                await plugin.save()


async def _migrate_plugin_manager(plugin_file) -> None:
    """迁移插件管理器数据

    参数:
        plugin_file: 插件管理器文件路径
    """
    import aiofiles

    async with aiofiles.open(plugin_file, encoding="utf8") as f:
        if not (data := json.loads(await f.read())):
            return

        logger.info("开始迁移插件数据...")

        plugins = await PluginInfo.filter().where_in("module", list(data.keys())).all()

        for plugin in plugins:
            if plugin_data := data.get(plugin.module):
                plugin.status = plugin_data.get("status", True)
                plugin.block_type = _parse_block_type(plugin_data.get("block_type"))
                await plugin.save()


async def group_migration() -> None:
    """迁移群组数据"""
    import aiofiles

    data_path = DATA_PATH / "manager" / "group_console.json"

    if not data_path.exists():
        return

    async with aiofiles.open(data_path, encoding="utf8") as f:
        if not (data := json.loads(await f.read())):
            return

        logger.info("开始迁移群组数据...")

        for group_data in data:
            group_info = await GroupConsole.filter(
                group_id=group_data["group_id"]
            ).first()

            if group_info:
                await _update_group_info(group_info, group_data)
            else:
                await _create_group_info(group_data)

        await _migrate_task_info(data)

        data_path.unlink()
        logger.info("迁移群组数据完成!")


async def _update_group_info(group_info: GroupConsole, group_data: dict) -> None:
    """更新群组信息

    参数:
        group_info: 群组信息实例
        group_data: 群组数据字典
    """
    group_info.group_name = group_data.get("group_name", group_info.group_name)
    group_info.member_count = group_data.get("member_count", group_info.member_count)
    group_info.max_member_count = group_data.get(
        "max_member_count", group_info.max_member_count
    )
    group_info.level = group_data.get("level", group_info.level)
    group_info.status = group_data.get("status", group_info.status)
    group_info.is_super = group_data.get("is_super", group_info.is_super)
    await group_info.save()


async def _create_group_info(group_data: dict) -> None:
    """创建群组信息

    参数:
        group_data: 群组数据字典
    """
    await GroupConsole.create(
        group_id=group_data["group_id"],
        group_name=group_data.get("group_name", ""),
        member_count=group_data.get("member_count", 0),
        max_member_count=group_data.get("max_member_count", 0),
        level=group_data.get("level", 5),
        status=group_data.get("status", True),
        is_super=group_data.get("is_super", False),
    )


async def _migrate_task_info(data: list[dict]) -> None:
    """迁移任务信息

    参数:
        data: 任务数据列表
    """
    for task_info in data:
        if not (
            task_list := [t for t in task_info.get("task_list", []) if t.get("module")]
        ):
            continue

        module_list = [t["module"] for t in task_list]
        tasks = await TaskInfo.filter().where_in("module", module_list).all()

        for task in tasks:
            task.status = task_info.get("status", True)
            task.load_status = task_info.get("load_status", True)
            await task.save()
