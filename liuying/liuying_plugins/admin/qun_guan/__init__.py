from arclet.alconna import Args
from nonebot.adapters import Bot
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import (
    Alconna,
    Arparma,
    At,
    Match,
    on_alconna,
)
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import PluginExtraData
from liuying.models._user import UserPermLevel
from liuying.utils.enum import PluginType
from liuying.utils.message import MessageUtils
from liuying.utils.rules import admin_check

from ._data_source import QunGuanManage

__plugin_meta__ = PluginMetadata(
    name="QunGuan",
    description="群管功能，支持禁言和踢人",
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
        version="1.0",
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


def _resolve_target(user: Match[At | str]) -> str:
    """从 Match 中解析目标用户ID"""
    match user.result:
        case At() as at:
            return at.target
        case str() as s:
            return s
        case _:
            return str(user.result)


async def _check_permission(
    bot: Bot, session: Uninfo, target_user_id: str
) -> str | None:
    """检查操作权限，返回错误信息或None"""
    if not session.group:
        return "此命令仅在群聊中有效"

    bot_id = bot.self_id
    operator_level = await UserPermLevel.get_level(
        session.user.id, bot_id, session.group.id
    )
    target_level = await UserPermLevel.get_level(
        target_user_id, bot_id, session.group.id
    )

    if operator_level < 5:
        return "杂鱼, 你的权限不足"
    if target_level >= 5:
        return "不能操作5级权限的用户"
    return None


_mute_matcher = on_alconna(
    Alconna(
        "禁言",
        Args["user", [At, str]],
        Args["duration", int, 30],
    ),
    aliases={"禁"},
    rule=admin_check(5),
    priority=50,
    block=True,
)

_unmute_matcher = on_alconna(
    Alconna(
        "解禁",
        Args["user", [At, str]],
    ),
    aliases={"解"},
    rule=admin_check(5),
    priority=50,
    block=True,
)

_kick_matcher = on_alconna(
    Alconna(
        "踢",
        Args["user", [At, str]],
    ),
    aliases={"踢了", "踢人"},
    rule=admin_check(5),
    priority=50,
    block=True,
)


@_mute_matcher.handle()
async def _(
    bot: Bot,
    session: Uninfo,
    arparma: Arparma,
    user: Match[At | str],
    duration: Match[int],
):
    """处理禁言命令"""
    target_user_id = _resolve_target(user)
    if error := await _check_permission(bot, session, target_user_id):
        await MessageUtils.build_message(error).finish(reply_to=True)

    result = await QunGuanManage.mute_user(
        bot=bot,
        group_id=session.group.id,
        user_id=target_user_id,
        duration=duration.result,
        operator_id=session.user.id,
    )
    await MessageUtils.build_message(result).finish(reply_to=True)


@_unmute_matcher.handle()
async def _(
    bot: Bot,
    session: Uninfo,
    arparma: Arparma,
    user: Match[At | str],
):
    """处理解禁命令"""
    target_user_id = _resolve_target(user)
    if error := await _check_permission(bot, session, target_user_id):
        await MessageUtils.build_message(error).finish(reply_to=True)

    result = await QunGuanManage.unmute_user(
        bot=bot,
        group_id=session.group.id,
        user_id=target_user_id,
        operator_id=session.user.id,
    )
    await MessageUtils.build_message(result).finish(reply_to=True)


@_kick_matcher.handle()
async def _(
    bot: Bot,
    session: Uninfo,
    arparma: Arparma,
    user: Match[At | str],
):
    """处理踢人命令"""
    target_user_id = _resolve_target(user)
    if error := await _check_permission(bot, session, target_user_id):
        await MessageUtils.build_message(error).finish(reply_to=True)

    result = await QunGuanManage.kick_user(
        bot=bot,
        group_id=session.group.id,
        user_id=target_user_id,
        operator_id=session.user.id,
    )
    await MessageUtils.build_message(result).finish(reply_to=True)
