"""
帮助数据源模块
"""
from pathlib import Path

import nonebot
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import PluginExtraData
from liuying.models._user import UserLevel
from liuying.models.plugin_info import PluginInfo
from liuying.models.statistics import Statistics
from liuying.utils.enum import PluginType
from liuying.utils.image import BuildImage

from ._config import (
    GROUP_HELP_PATH,
    SIMPLE_DETAIL_HELP_IMAGE,
    SIMPLE_HELP_IMAGE,
    driver,
)
from ._render import build_help_image


async def create_help_image(
    session: Uninfo, group_id: str | None, is_detail: bool
) -> Path:
    """
    生成帮助图片

    参数:
        session: Uninfo
        group_id: 群号
        is_detail: 是否详细

    返回:
        Path: 图片保存路径
    """
    image_data = await build_help_image(session, group_id, is_detail)
    result = BuildImage.open(image_data)

    save_path = _get_save_path(group_id, is_detail)
    await result.save(save_path)
    return save_path


def _get_save_path(group_id: str | None, is_detail: bool) -> Path:
    """
    获取帮助图片保存路径

    参数:
        group_id: 群号
        is_detail: 是否详细

    返回:
        Path: 保存路径
    """
    match (group_id, is_detail):
        case (str(gid), _):
            return GROUP_HELP_PATH / f"{gid}_{is_detail}.png"
        case (None, True):
            return SIMPLE_DETAIL_HELP_IMAGE
        case _:
            return SIMPLE_HELP_IMAGE


async def get_user_allowed_types(user_id: str) -> list[PluginType]:
    """
    获取用户可访问插件类型列表

    参数:
        user_id: 用户id

    返回:
        list[PluginType]: 插件类型列表
    """
    types = [PluginType.NORMAL, PluginType.DEPENDANT]

    user_levels = await UserLevel.filter(
        user_id=user_id, user_level__gt=0
    ).exists()

    if user_levels:
        types.extend([PluginType.ADMIN, PluginType.SUPER_AND_ADMIN])

    if user_id in driver.config.superusers:
        types.append(PluginType.SUPERUSER)

    return types


async def get_plugin_help_detail(
    user_id: str, name: str, is_superuser: bool
) -> str | bytes:
    """
    获取功能的帮助信息

    参数:
        user_id: 用户id
        name: 插件名称或id
        is_superuser: 是否为超级用户

    返回:
        str | bytes: 帮助信息
    """
    allowed_types = await get_user_allowed_types(user_id)
    plugin = await _find_plugin(name, allowed_types)

    if not plugin:
        return "没有查找到这个功能噢..."

    return await _build_help_detail(plugin, is_superuser, user_id)


async def _find_plugin(
    name: str, allowed_types: list[PluginType]
) -> PluginInfo | None:
    """
    查找插件

    参数:
        name: 插件名称或id
        allowed_types: 允许的插件类型列表

    返回:
        PluginInfo | None: 插件信息
    """
    if name.isdigit():
        return await PluginInfo.filter(
            id=int(name), plugin_type__in=allowed_types,
        ).first()

    return await PluginInfo.filter(
        name__iexact=name,
        load_status=True,
        plugin_type__in=allowed_types,
    ).first()


async def _build_help_detail(
    plugin: PluginInfo, is_superuser: bool, user_id: str
) -> str | bytes:
    """构建帮助详情

    参数:
        plugin: 插件信息
        is_superuser: 是否为超级用户
        user_id: 用户ID

    返回:
        str | bytes: 帮助详情
    """
    nb_plugin = nonebot.get_plugin_by_module_name(plugin.module_path)

    if not nb_plugin or not nb_plugin.metadata:
        return "糟糕! 该功能没有帮助喔..."

    extra_data = PluginExtraData(**nb_plugin.metadata.extra)

    if is_superuser and not extra_data.superuser_help:
        return "该功能没有超级用户帮助信息"

    usage = extra_data.superuser_help if is_superuser else nb_plugin.metadata.usage
    call_count = await Statistics.filter(
        plugin_name=plugin.module
    ).count()

    template_data = {
        "title": nb_plugin.metadata.name,
        "author": extra_data.author,
        "version": extra_data.version,
        "call_count": call_count,
        "descriptions": _format_text(nb_plugin.metadata.description),
        "usages": _format_text(usage),
    }

    from liuying.ui import render
    return await render(
        "pages/builtin/help_detail", template_data,
        user_id=user_id, wait=2,
    )


def _format_text(text: str) -> list[str]:
    """
    格式化文本，移除多余空格

    参数:
        text: 原始文本

    返回:
        list[str]: 格式化后的文本列表
    """
    lines = text.split("\n")
    min_spaces = min(
        (len(line) - len(line.lstrip(" ")) for line in lines if line.strip()),
        default=0,
    )

    return [
        line[min_spaces:]
        for line in lines
    ]


async def search_plugins(
    user_id: str, keyword: str, is_superuser: bool
) -> list[dict[str, str]]:
    """
    搜索插件

    参数:
        user_id: 用户id
        keyword: 搜索关键词
        is_superuser: 是否为超级用户

    返回:
        list[dict[str, str]]: 搜索结果列表
    """
    allowed_types = await get_user_allowed_types(user_id)

    plugins = await PluginInfo.filter(
        name__icontains=keyword,
        load_status=True,
        plugin_type__in=allowed_types,
    ).all()

    return [
        {"id": str(plugin.id), "name": plugin.name}
        for plugin in plugins
    ]
