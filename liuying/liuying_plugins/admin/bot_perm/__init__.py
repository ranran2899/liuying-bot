"""用户权限管理插件

合并用户全局/群组权限与机器人用户权限的管理指令。
"""

from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    At,
    Match,
    Option,
    on_alconna,
)
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import PluginExtraData
from liuying.utils.enum import PluginType
from liuying.utils.message import MessageUtils
from liuying.utils.rules import admin_check

from ._data_source import PermManage

__plugin_meta__ = PluginMetadata(
    name="用户权限管理",
    description="管理用户全局/群组权限与指定机器人的用户权限",
    usage="""
    添加权限 [level] [@user/用户id] -g [群号]      # 添加指定群权限
    添加权限 [level] [@user/用户id] -g            # 添加当前群权限
    添加权限 [level] [@user/用户id]               # 添加用户全局权限
    删除权限 [@user/用户id] [-g [群号]]           # 删除用户权限
    bot添加权限 [bot_id] [level] [@user/用户id]   # 为指定机器人添加用户权限
    bot删除权限 [bot_id] [@user/用户id]           # 删除指定机器人的用户权限
    bot查询权限 [bot_id] [@user/用户id]           # 查询用户在指定机器人的权限
    """,
    extra=PluginExtraData(
        author="liuying",
        version="1.1",
        plugin_type=PluginType.SUPER_AND_ADMIN,
        admin_level=10,
    ).to_dict(),
)


_add_matcher = on_alconna(
    Alconna(
        "添加权限",
        Args["level", int]["uid", [str, At]],
        Option(
            "-g|--group",
            Args["gid", str],
            default=None,
            help_text="指定群组（不指定则为全局权限，不填群号则为当前群）",
        ),
    ),
    rule=admin_check(10),
    priority=5,
    block=True,
)


_delete_matcher = on_alconna(
    Alconna(
        "删除权限",
        Args["uid", [str, At]],
        Option(
            "-g|--group",
            Args["gid", str],
            default=None,
            help_text="指定群组（不指定则为全局权限，不填群号则为当前群）",
        ),
    ),
    rule=admin_check(10),
    priority=5,
    block=True,
)


_bot_add_matcher = on_alconna(
    Alconna(
        "bot添加权限",
        Args["bot_id", str],
        Args["level", int],
        Args["uid", [str, At]],
    ),
    rule=admin_check(10),
    priority=5,
    block=True,
)


_bot_delete_matcher = on_alconna(
    Alconna(
        "bot删除权限",
        Args["bot_id", str],
        Args["uid", [str, At]],
    ),
    rule=admin_check(10),
    priority=5,
    block=True,
)


_bot_query_matcher = on_alconna(
    Alconna(
        "bot查询权限",
        Args["bot_id", str],
        Args["uid", [str, At]],
    ),
    rule=admin_check(10),
    priority=5,
    block=True,
)


@_add_matcher.handle()
async def handle_add_permission(
    session: Uninfo,
    level: int,
    uid: str | At,
    gid: Match[str],
):
    """处理添加权限指令"""
    result = await PermManage.add_permission(session, uid, level, gid)
    await MessageUtils.build_message(result).finish(reply_to=True)


@_delete_matcher.handle()
async def handle_delete_permission(
    session: Uninfo,
    uid: str | At,
    gid: Match[str],
):
    """处理删除权限指令"""
    result = await PermManage.delete_permission(session, uid, gid)
    await MessageUtils.build_message(result).finish(reply_to=True)


@_bot_add_matcher.handle()
async def handle_bot_add_permission(
    session: Uninfo,
    bot_id: str,
    level: int,
    uid: str | At,
):
    """处理添加机器人用户权限指令"""
    result = await PermManage.add_bot_permission(session, bot_id, uid, level)
    await MessageUtils.build_message(result).finish()


@_bot_delete_matcher.handle()
async def handle_bot_delete_permission(
    session: Uninfo,
    bot_id: str,
    uid: str | At,
):
    """处理删除机器人用户权限指令"""
    result = await PermManage.delete_bot_permission(session, bot_id, uid)
    await MessageUtils.build_message(result).finish()


@_bot_query_matcher.handle()
async def handle_bot_query_permission(
    session: Uninfo,
    bot_id: str,
    uid: str | At,
):
    """处理查询机器人用户权限指令"""
    result = await PermManage.query_bot_permission(session, bot_id, uid)
    await MessageUtils.build_message(result).finish()
