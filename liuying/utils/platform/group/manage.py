"""统一群管理的平台实现

各平台群管理接口差异较大，统一按 bot.adapter.name 分发：
- OneBot V11/V12: set_group_ban / set_group_kick
- QQ官方: /v2/groups/{group_openid}/restrict_chat_setting 禁言（内邀接口，
  未开通权限时平台返回错误码11253，最长30天）、
  /v2/groups/{group_openid}/batch_remove_members 踢人（内邀接口，单次最多20个）
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from nonebot.adapters import Bot
from nonebot.drivers import Request

from liuying.utils.log import logger


async def ban_user(bot: Bot, user_id: str, group_id: str, duration: int) -> None:
    """统一群禁言，按适配器分发到各平台实现

    参数:
        bot: Bot
        user_id: 用户id（QQ官方适配器为成员openid）
        group_id: 群组id（QQ官方适配器为群openid）
        duration: 禁言时长(分钟)
    """
    match bot.adapter.name:
        case "OneBot V11" | "OneBot V12":
            await _ban_onebot(bot, user_id, group_id, duration)
        case "QQ":
            await _ban_qq_official(bot, user_id, group_id, duration)
        case _:
            logger.warning(
                f"适配器 {bot.adapter.name} 暂不支持禁言，已忽略",
                command="GroupManage",
                group_id=group_id,
                user_id=user_id,
            )


async def kick_user(
    bot: Bot,
    user_id: str,
    group_id: str,
    *,
    reject_add_request: bool = False,
) -> None:
    """统一踢出群成员，按适配器分发到各平台实现

    参数:
        bot: Bot
        user_id: 用户id（QQ官方适配器为成员openid）
        group_id: 群组id（QQ官方适配器为群openid）
        reject_add_request: 是否拒绝该用户再次入群（QQ官方适配器即加入群黑名单）
    """
    match bot.adapter.name:
        case "OneBot V11" | "OneBot V12":
            await _kick_onebot(bot, user_id, group_id, reject_add_request)
        case "QQ":
            await _kick_qq_official(bot, user_id, group_id, reject_add_request)
        case _:
            logger.warning(
                f"适配器 {bot.adapter.name} 暂不支持踢出群成员，已忽略",
                command="GroupManage",
                group_id=group_id,
                user_id=user_id,
            )


async def _ban_onebot(
    bot: Bot, user_id: str, group_id: str, duration: int
) -> None:
    """OneBot V11/V12 禁言"""
    await bot.set_group_ban(
        group_id=group_id,
        user_id=user_id,
        duration=duration * 60,
    )


# QQ官方禁言最大时长30天(分钟)，到期时间使用东八区RFC3339格式
_QQ_MAX_MINUTES = 30 * 24 * 60
_QQ_TZ = timezone(timedelta(hours=8))


async def _ban_qq_official(
    bot: Bot, user_id: str, group_id: str, duration: int
) -> None:
    """QQ官方禁言，user_id/group_id 均为openid"""
    duration = min(max(1, duration), _QQ_MAX_MINUTES)
    expire_at = (datetime.now(_QQ_TZ) + timedelta(minutes=duration)).isoformat()
    await _qq_post(
        bot,
        f"v2/groups/{group_id}/restrict_chat_setting",
        {
            "members": [
                {"op": "add", "member_openid": user_id, "mute_expire_at": expire_at}
            ]
        },
    )


async def _kick_onebot(
    bot: Bot, user_id: str, group_id: str, reject_add_request: bool
) -> None:
    """OneBot V11/V12 踢出群成员"""
    await bot.set_group_kick(
        group_id=group_id,
        user_id=user_id,
        reject_add_request=reject_add_request,
    )


async def _kick_qq_official(
    bot: Bot, user_id: str, group_id: str, reject_add_request: bool
) -> None:
    """QQ官方踢出群成员，即批量移除接口单成员场景，user_id/group_id 均为openid"""
    await _qq_post(
        bot,
        f"v2/groups/{group_id}/batch_remove_members",
        {
            "member_openids": [user_id],
            "add_to_member_blacklist": reject_add_request,
        },
    )


async def _qq_post(bot: Bot, path: str, json_body: dict[str, Any]) -> Any:
    """调用QQ开放平台POST接口

    适配器未封装以上API，复用其请求管道自动携带QQBot鉴权并刷新token

    参数:
        bot: Bot
        path: 接口路径(相对api_base)
        json_body: 请求体

    返回:
        Any: 接口响应解析结果
    """
    request = Request(
        "POST",
        bot.adapter.get_api_base().joinpath(path),
        json=json_body,
    )
    return await bot._request(request)
