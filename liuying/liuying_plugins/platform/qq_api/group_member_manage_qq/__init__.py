from collections.abc import Awaitable, Callable

from nonebot.adapters.qq import Bot
from nonebot.adapters.qq import Event as QQEvent
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
from liuying.utils.rules import admin_check, ensure_group, notice_rule

from .data_source import GroupMuteManage

__plugin_meta__ = PluginMetadata(
    name="QQ官方群成员禁言",
    description="QQ官方平台群管功能，支持禁言和解禁成员",
    usage="""
    管理员命令
        格式:
        禁言 [At用户] [时间(分钟)]   : 禁言指定用户
        解禁 [At用户]               : 解除用户禁言

        示例:
        禁言 @用户 30               : 禁言用户30分钟
        解禁 @用户                  : 解除用户禁言
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="1.0",
        admin_level=5,
        plugin_type=PluginType.SUPER_AND_ADMIN,
    ).to_dict(),
)


_rule = admin_check(5) & ensure_group & notice_rule(QQEvent)


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


def _resolve_target(user: Match[At | str]) -> str:
    """从 Match 中解析目标用户openid"""
    return user.result.target if isinstance(user.result, At) else str(user.result)


async def _handle(
    bot: Bot,
    session: Uninfo,
    user: Match[At | str],
    operate: Callable[[str, str], Awaitable[str]],
) -> None:
    """通用处理：解析目标用户、校验权限并执行操作

    参数:
        bot: Bot实例
        session: 会话信息
        user: 目标用户匹配结果
        operate: 接收群openid与成员openid并返回结果消息的操作
    """
    target_user_id = _resolve_target(user)
    group_id = session.group.id if session.group else ""
    if await UserPermLevel.get_level(target_user_id, bot.self_id, group_id) >= 5:
        await MessageUtils.build_message("不能操作5级权限的用户").finish(reply_to=True)

    result = await operate(group_id, target_user_id)
    await MessageUtils.build_message(result).finish(reply_to=True)


@_mute_matcher.handle()
async def _(bot: Bot, session: Uninfo, user: Match[At | str], duration: Match[int]):
    """处理禁言命令"""
    await _handle(
        bot,
        session,
        user,
        lambda group_id, user_id: GroupMuteManage.mute_user(
            bot=bot,
            group_openid=group_id,
            member_openid=user_id,
            duration=duration.result,
            operator_id=session.user.id,
        ),
    )


@_unmute_matcher.handle()
async def _(bot: Bot, session: Uninfo, user: Match[At | str]):
    """处理解禁命令"""
    await _handle(
        bot,
        session,
        user,
        lambda group_id, user_id: GroupMuteManage.unmute_user(
            bot=bot,
            group_openid=group_id,
            member_openid=user_id,
            operator_id=session.user.id,
        ),
    )
