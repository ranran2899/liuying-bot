from nonebot.adapters import Bot
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    At,
    Match,
    on_alconna,
)
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import PluginExtraData
from liuying.models._user import UserPermLevel
from liuying.utils.enum import PluginType
from liuying.utils.message import MessageUtils
from liuying.utils.platform import PlatformUtils
from liuying.utils.rules import admin_check, ensure_group

__plugin_meta__ = PluginMetadata(
    name="群成员管理",
    description="群管功能，支持禁言、解禁和踢出成员",
    usage="""
    管理员命令
        格式:
        禁言 [At用户] [时间(分钟)]   : 禁言指定用户
        解禁 [At用户]               : 解除用户禁言
        踢 [At用户]                 : 踢出指定用户

        示例:
        禁言 @用户 30               : 禁言用户30分钟
        解禁 @用户                  : 解除用户禁言
        踢 @用户                    : 踢出用户
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="3.0",
        admin_level=5,
        plugin_type=PluginType.SUPER_AND_ADMIN,
        superuser_help="""
        超级管理员额外命令
        格式:
        禁言 [At用户/用户Id] [时间(分钟)]   : 禁言指定用户
        解禁 [At用户/用户Id]               : 解除用户禁言
        踢 [At用户/用户Id]                 : 踢出指定用户

        示例:
        禁言 123456789 30                 : 禁言用户123456789，30分钟
        解禁 123456789                    : 解除用户123456789的禁言
        踢 123456789                      : 踢出用户123456789
        """,
    ).to_dict(),
)


_rule = admin_check(5) & ensure_group


_mute_matcher = on_alconna(
    Alconna(
        "禁言",
        Args["user", [At, str]],
        Args["duration", int, 30],
    ),
    aliases={"禁"},
    rule=_rule,
    priority=50,
    block=True,
)

_unmute_matcher = on_alconna(
    Alconna(
        "解禁",
        Args["user", [At, str]],
    ),
    aliases={"解"},
    rule=_rule,
    priority=50,
    block=True,
)

_kick_matcher = on_alconna(
    Alconna(
        "踢",
        Args["user", [At, str]],
    ),
    aliases={"踢了", "踢人"},
    rule=_rule,
    priority=50,
    block=True,
)


def _resolve_target(user: Match[At | str]) -> str:
    """从 Match 中解析目标用户ID"""
    return user.result.target if isinstance(user.result, At) else str(user.result)


@_mute_matcher.handle()
async def _(bot: Bot, session: Uninfo, user: Match[At | str], duration: Match[int]):
    """处理禁言命令"""
    target_user_id = _resolve_target(user)
    group_id = session.group.id if session.group else ""
    if await UserPermLevel.get_level(target_user_id, bot.self_id, group_id) >= 5:
        await MessageUtils.build_message("不能禁言5级的管理员").finish(reply_to=True)

    minutes = max(1, duration.result)
    await PlatformUtils.ban_group_user(bot, target_user_id, group_id, minutes)
    await MessageUtils.build_message(
        f"已将 {target_user_id} 禁言 {minutes} 分钟"
    ).finish(reply_to=True)


@_unmute_matcher.handle()
async def _(bot: Bot, session: Uninfo, user: Match[At | str]):
    """处理解禁命令"""
    target_user_id = _resolve_target(user)
    group_id = session.group.id if session.group else ""
    if await UserPermLevel.get_level(target_user_id, bot.self_id, group_id) >= 5:
        await MessageUtils.build_message("不能帮解禁5级权限的用户哦~").finish(reply_to=True)

    await PlatformUtils.unban_group_user(bot, target_user_id, group_id)
    await MessageUtils.build_message(f"已将 {target_user_id} 解禁").finish(
        reply_to=True
    )


@_kick_matcher.handle()
async def _(bot: Bot, session: Uninfo, user: Match[At | str]):
    """处理踢人命令"""
    target_user_id = _resolve_target(user)
    group_id = session.group.id if session.group else ""
    if await UserPermLevel.get_level(target_user_id, bot.self_id, group_id) >= 5:
        await MessageUtils.build_message("无法踢出5级权限的用户").finish(reply_to=True)

    await PlatformUtils.kick_group_user(bot, target_user_id, group_id)
    await MessageUtils.build_message(f"已将 {target_user_id} 踢出群聊").finish(
        reply_to=True
    )
