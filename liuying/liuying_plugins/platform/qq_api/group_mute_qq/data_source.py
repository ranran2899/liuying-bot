"""QQ官方适配器群成员禁言

适配器未封装群禁言API,直接调用QQ开放平台接口实现:
- POST /v2/groups/{group_openid}/restrict_chat_setting 设置群成员禁言
机器人需拥有群管理员身份,最大禁言时长30天
该能力为内邀接口,未开通权限时平台返回错误码11253(应用无接口访问权限)
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from nonebot.adapters import Bot
from nonebot.drivers import Request

from liuying.utils.log import logger

# 禁言最大时长30天(分钟)
_MAX_MUTE_MINUTES = 30 * 24 * 60

# 禁言到期时间使用东八区,RFC3339格式
_TZ = timezone(timedelta(hours=8))


class GroupMuteManage:
    """QQ官方群成员禁言管理"""

    @classmethod
    async def _post(cls, bot: Bot, path: str, json_body: dict[str, Any]):
        """调用QQ开放平台POST接口

        复用适配器的请求管道,自动携带QQBot鉴权头并处理token过期刷新

        参数:
            bot: Bot实例
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

    @classmethod
    async def mute_user(
        cls,
        bot: Bot,
        group_openid: str,
        member_openid: str,
        duration: int,
        operator_id: str,
    ) -> str:
        """禁言用户

        参数:
            bot: Bot实例
            group_openid: 群openid
            member_openid: 成员openid
            duration: 禁言时长(分钟)
            operator_id: 操作者ID

        返回:
            str: 操作结果信息
        """
        duration = min(max(1, duration), _MAX_MUTE_MINUTES)
        try:
            expire_at = (
                datetime.now(_TZ) + timedelta(minutes=duration)
            ).isoformat()
            await cls._post(
                bot,
                f"v2/groups/{group_openid}/restrict_chat_setting",
                {
                    "members": [
                        {
                            "op": "add",
                            "member_openid": member_openid,
                            "mute_expire_at": expire_at,
                        }
                    ]
                },
            )

            logger.info(
                f"管理员 {operator_id} 禁言用户 {member_openid} {duration} 分钟",
                "QQ官方群成员禁言",
                session=operator_id,
                group_id=group_openid,
            )
            return f"已将用户 {member_openid} 禁言 {duration} 分钟"

        except Exception as e:
            logger.error(
                "禁言用户失败",
                "QQ官方群成员禁言",
                session=operator_id,
                group_id=group_openid,
                e=e,
            )
            return f"禁言用户失败: {e!s}"

    @classmethod
    async def unmute_user(
        cls,
        bot: Bot,
        group_openid: str,
        member_openid: str,
        operator_id: str,
    ) -> str:
        """解除用户禁言

        参数:
            bot: Bot实例
            group_openid: 群openid
            member_openid: 成员openid
            operator_id: 操作者ID

        返回:
            str: 操作结果信息
        """
        try:
            await cls._post(
                bot,
                f"v2/groups/{group_openid}/restrict_chat_setting",
                {
                    "members": [
                        {
                            "op": "del",
                            "member_openid": member_openid,
                            "mute_expire_at": "",
                        }
                    ]
                },
            )

            logger.info(
                f"管理员 {operator_id} 解除用户 {member_openid} 的禁言",
                "QQ官方群成员禁言",
                session=operator_id,
                group_id=group_openid,
            )
            return f"已解除用户 {member_openid} 的禁言"

        except Exception as e:
            logger.error(
                "解除用户禁言失败",
                "QQ官方群成员禁言",
                session=operator_id,
                group_id=group_openid,
                e=e,
            )
            return f"解除用户禁言失败: {e!s}"
