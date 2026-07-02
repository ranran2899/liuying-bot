"""
帮助插件工具模块
"""
from collections.abc import Callable

from nonebot_plugin_uninfo import Uninfo

from liuying.models._bot import BotConsole
from liuying.models._group import GroupConsole
from liuying.models.plugin_info import PluginInfo
from liuying.utils.enum import PluginType


async def classify_plugins_by_type(
    plugin_types: list[PluginType] | None = None,
) -> dict[str, list[PluginInfo]]:
    """
    对插件按照菜单类型分类

    参数:
        plugin_types: 插件类型列表，默认为 [PluginType.NORMAL, PluginType.DEPENDANT]

    返回:
        dict[str, list[PluginInfo]]: 分类后的插件数据
    """
    if plugin_types is None:
        plugin_types = [PluginType.NORMAL, PluginType.DEPENDANT]

    plugins = await PluginInfo.filter(
        menu_type__ne="",
        load_status=True,
        plugin_type__in=plugin_types,
        is_show=True,
    ).all()

    classified: dict[str, list[PluginInfo]] = {}
    for plugin in plugins:
        menu_type = plugin.menu_type or "功能"
        if menu_type == "normal":
            menu_type = "功能"
        classified.setdefault(menu_type, []).append(plugin)

    return classified


async def process_plugins(
    session: Uninfo,
    group_id: str | None,
    is_detail: bool,
    handler: Callable,
    plugin_types: list[PluginType] | None = None,
) -> dict[str, list]:
    """
    对插件进行分类并判断状态

    参数:
        session: Uninfo对象
        group_id: 群组id
        is_detail: 是否详细帮助
        handler: 回调方法
        plugin_types: 插件类型列表，默认为 [PluginType.NORMAL, PluginType.DEPENDANT]

    返回:
        dict[str, list]: 分类插件数据
    """
    classified_plugins = await classify_plugins_by_type(plugin_types)
    result: dict[str, list] = {}

    group = (
        await GroupConsole.filter(group_id=group_id).first()
        if group_id
        else None
    )
    bot = await BotConsole.filter(bot_id=session.self_id).first()

    for menu, plugins in classified_plugins.items():
        result.setdefault(menu, []).extend(
            handler(bot, plugin, group, is_detail) for plugin in plugins
        )

    for items in result.values():
        items.sort(key=lambda x: x.id)

    return result
