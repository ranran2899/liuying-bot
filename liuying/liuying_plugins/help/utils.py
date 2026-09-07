"""
帮助插件工具模块
"""
from collections.abc import Callable

from nonebot_plugin_uninfo import Uninfo

from liuying.models._bot import BotConsole
from liuying.models._group import GroupConsole
from liuying.models.plugin_info import PluginInfo
from liuying.utils.enum import PluginType


async def process_plugins(
    session: Uninfo,
    group_id: str | None,
    is_detail: bool,
    handler: Callable,
    plugin_types: list[PluginType] | None = None,
) -> dict[str, list]:
    """
    对插件按菜单类型分类并逐个构造展示数据

    参数:
        session: Uninfo对象
        group_id: 群组id
        is_detail: 是否详细帮助
        handler: 回调方法
        plugin_types: 插件类型列表，默认为 [PluginType.NORMAL, PluginType.DEPENDANT]

    返回:
        dict[str, list]: 分类插件数据
    """
    if plugin_types is None:
        plugin_types = [PluginType.NORMAL, PluginType.DEPENDANT]

    plugins = await PluginInfo.visible_query(
        menu_type__ne="",
        plugin_type__in=plugin_types,
    ).all()

    classified: dict[str, list[PluginInfo]] = {}
    for plugin in plugins:
        menu_type = plugin.menu_type or "功能"
        if menu_type == "normal":
            menu_type = "功能"
        classified.setdefault(menu_type, []).append(plugin)

    group = (
        await GroupConsole.filter(group_id=group_id).first()
        if group_id
        else None
    )
    bot = await BotConsole.filter(bot_id=session.self_id).first()

    result: dict[str, list] = {}
    for menu, menu_plugins in classified.items():
        result[menu] = [
            handler(bot, plugin, group, is_detail) for plugin in menu_plugins
        ]
        result[menu].sort(key=lambda x: x.id)

    return result
