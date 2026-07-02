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
from liuying.models._user import UserLevel
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
    if not session.group:
        await MessageUtils.build_message("此命令仅在群聊中有效").finish(reply_to=True)

    match user.result:
        case At() as at:
            target_user_id = at.target
        case str() as s:
            target_user_id = s
        case _:
            target_user_id = str(user.result)

    bot_id = bot.self_id

    operator_level = await UserLevel.get_level(
        session.user.id, bot_id, session.group.id
    )
    target_level = await UserLevel.get_level(target_user_id, bot_id, session.group.id)

    if operator_level < 5:
        await MessageUtils.build_message("杂鱼, 你的权限不足").finish(reply_to=True)
    if target_level >= 5:
        await MessageUtils.build_message("不能禁5级权限的用户").finish(reply_to=True)

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
    if not session.group:
        await MessageUtils.build_message("此命令仅在群聊中有效").finish(reply_to=True)

    match user.result:
        case At() as at:
            target_user_id = at.target
        case str() as s:
            target_user_id = s
        case _:
            target_user_id = str(user.result)

    bot_id = bot.self_id

    operator_level = await UserLevel.get_level(
        session.user.id, bot_id, session.group.id
    )
    target_level = await UserLevel.get_level(target_user_id, bot_id, session.group.id)

    if operator_level < 5:
        await MessageUtils.build_message("杂鱼, 你的权限不足").finish(reply_to=True)
    if target_level >= 5:
        await MessageUtils.build_message("不能帮解禁5级权限的用户").finish(
            reply_to=True
        )

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
    if not session.group:
        await MessageUtils.build_message("此命令仅在群聊中有效").finish(reply_to=True)

    match user.result:
        case At() as at:
            target_user_id = at.target
        case str() as s:
            target_user_id = s
        case _:
            target_user_id = str(user.result)

    bot_id = bot.self_id

    operator_level = await UserLevel.get_level(
        session.user.id, bot_id, session.group.id
    )
    target_level = await UserLevel.get_level(target_user_id, bot_id, session.group.id)

    if operator_level < 5:
        await MessageUtils.build_message("你的权限不足，需要5级权限才能踢人").finish(
            reply_to=True
        )
    if target_level >= 5:
        await MessageUtils.build_message("不能踢5级权限的用户").finish(reply_to=True)

    result = await QunGuanManage.kick_user(
        bot=bot,
        group_id=session.group.id,
        user_id=target_user_id,
        operator_id=session.user.id,
    )

    await MessageUtils.build_message(result).finish(reply_to=True)
