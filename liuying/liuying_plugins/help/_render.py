"""
帮助菜单渲染模块
"""
from datetime import datetime

import nonebot
from nonebot_plugin_uninfo import Uninfo
from pydantic import BaseModel

from liuying.configs.utils import PluginExtraData
from liuying.models._bot import BotConsole
from liuying.models._group import GroupConsole
from liuying.models.plugin_info import PluginInfo
from liuying.ui import render
from liuying.utils.enum import BlockType, PluginType

from ._utils import process_plugins


class PluginItem(BaseModel):
    """插件项数据模型"""
    plugin_name: str
    commands: list[str]
    id: str
    status: bool
    has_superuser_help: bool


def _create_plugin_item(
    bot: BotConsole | None,
    plugin: PluginInfo,
    group: GroupConsole | None,
    is_detail: bool,
) -> PluginItem:
    """
    构造插件项

    参数:
        bot: BotConsole
        plugin: PluginInfo
        group: 群组
        is_detail: 是否为详细

    返回:
        PluginItem: 插件项
    """
    status = True
    has_superuser_help = False
    commands: list[str] = []

    nb_plugin = nonebot.get_plugin_by_module_name(plugin.module_path)
    if nb_plugin and nb_plugin.metadata:
        extra_data = PluginExtraData(**nb_plugin.metadata.extra)
        has_superuser_help = bool(extra_data.superuser_help)
        if is_detail:
            commands = [cmd.command for cmd in extra_data.commands]

    match plugin.block_type if not plugin.status else None:
        case BlockType.ALL:
            status = False
        case BlockType.GROUP if group:
            status = False
        case BlockType.PRIVATE if not group:
            status = False
        case _:
            if group and f"{plugin.module}," in group.block_plugin:
                status = False
            elif bot and f"{plugin.module}," in bot.block_plugins:
                status = False

    return PluginItem(
        plugin_name=plugin.name,
        commands=commands,
        id=str(plugin.id),
        status=status,
        has_superuser_help=has_superuser_help,
    )


def _build_frontend_data(classified: dict[str, list[PluginItem]]) -> list[dict]:
    """
    构建前端插件数据

    参数:
        classified: 插件数据

    返回:
        list[dict]: 前端插件数据
    """
    if not classified:
        return []

    sorted_classified = dict(
        sorted(classified.items(), key=lambda x: len(x[1]), reverse=True)
    )

    menu_items = [
        {
            "name": "主要功能" if menu in ["normal", "功能"] else menu,
            "items": items,
        }
        for menu, items in sorted_classified.items()
    ]

    for item in menu_items:
        if isinstance(item["items"], list):
            item["items"].sort(key=lambda x: x.id)

    return menu_items


async def build_help_image(
    session: Uninfo,
    group_id: str | None,
    is_detail: bool,
    plugin_types: list[PluginType] | None = None,
    menu_title: str | None = None,
    template_path: str = "pages/builtin/help",
) -> bytes:
    """
    构造帮助菜单图片

    参数:
        session: 会话信息
        group_id: 群号
        is_detail: 是否详细帮助
        plugin_types: 插件类型列表，默认为 [PluginType.NORMAL, PluginType.DEPENDANT]
        menu_title: 菜单标题，默认根据插件类型自动生成
        template_path: 模板路径，默认为 "pages/builtin/help"

    返回:
        bytes: 图片数据
    """
    if plugin_types is None:
        plugin_types = [PluginType.NORMAL, PluginType.DEPENDANT]

    if menu_title is None:
        menu_title = _get_menu_title(plugin_types)

    classified = await process_plugins(
        session, group_id, is_detail, _create_plugin_item, plugin_types
    )
    plugin_list = _build_frontend_data(classified)

    plugin_count = sum(
        len(p["items"]) for p in plugin_list if isinstance(p.get("items"), list)
    )
    available_count = sum(
        sum(1 for item in p["items"] if item.status)
        for p in plugin_list
        if isinstance(p.get("items"), list)
    )

    template_data = {
        "plugin_list": plugin_list,
        "width": 637,
        "font_size": (53, 19),
        "is_detail": is_detail,
        "plugin_count": plugin_count,
        "available_count": available_count,
        "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "menu_title": menu_title,
    }

    return await render(
        template_path,
        template_data,
        user_id=session.user.id,
        wait=2,
    )


def _get_menu_title(plugin_types: list[PluginType]) -> str:
    """
    根据插件类型获取菜单标题

    参数:
        plugin_types: 插件类型列表

    返回:
        str: 菜单标题
    """
    match plugin_types:
        case types if PluginType.SUPERUSER in types:
            return "超级用户帮助"
        case types if PluginType.ADMIN in types:
            return "管理员帮助"
        case types if PluginType.SUPER_AND_ADMIN in types:
            return "管理员以及超级用户帮助"
        case _:
            return "流萤帮助"


async def build_admin_help(
    session: Uninfo,
    group_id: str | None,
    is_detail: bool = False,
    menu_title: str = "管理员菜单",
) -> bytes:
    """
    构造管理员帮助图片

    参数:
        session: 会话信息
        group_id: 群号
        is_detail: 是否详细帮助
        menu_title: 菜单标题

    返回:
        bytes: 图片数据
    """
    return await build_help_image(
        session=session,
        group_id=group_id,
        is_detail=is_detail,
        plugin_types=[PluginType.ADMIN, PluginType.SUPER_AND_ADMIN],
        menu_title=menu_title,
    )


async def build_superuser_help(
    session: Uninfo,
    group_id: str | None,
    is_detail: bool = False,
    menu_title: str = "超级用户菜单",
) -> bytes:
    """
    构造超级用户帮助图片

    参数:
        session: 会话信息
        group_id: 群号
        is_detail: 是否详细帮助
        menu_title: 菜单标题

    返回:
        bytes: 图片数据
    """
    return await build_help_image(
        session=session,
        group_id=group_id,
        is_detail=is_detail,
        plugin_types=[PluginType.SUPERUSER],
        menu_title=menu_title,
    )
