import nonebot
from nonebot.adapters import Bot
from nonebot_plugin_alconna import SupportScope
from nonebot_plugin_alconna.uniseg import Receipt, Target, UniMessage
from nonebot_plugin_uninfo import Uninfo, get_interface

from liuying.configs.config import BotConfig
from liuying.utils.exception import NotFindSuperuser
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils


def _normalize_platform(scope: str) -> str:
    """将 scope 统一为平台标识"""
    platform = scope.lower()
    return "qq" if platform.startswith("qq") else platform


class PlatformUtils:
    @classmethod
    def is_qbot(cls, session: Uninfo | Bot) -> bool:
        """判断bot是否为qq官bot

        参数:
            session: Uninfo | Bot

        返回:
            bool: 是否为官bot
        """
        if isinstance(session, Bot):
            return bool(BotConfig.get_qbot_uid(session.self_id))
        return bool(BotConfig.get_qbot_uid(session.self_id)) or (
            session.scope == SupportScope.qq_api
        )

    @classmethod
    async def send_superuser(
        cls,
        bot: Bot | None,
        message: UniMessage | str,
        superuser_id: str | None = None,
    ) -> list[tuple[str, Receipt]]:
        """发送消息给超级用户

        参数:
            bot: Bot，没有传入时使用get_bot随机获取
            message: 消息
            superuser_id: 指定超级用户id.

        异常:
            NotFindSuperuser: 未找到超级用户id

        返回:
            list[tuple[str, Receipt]]: 发送结果列表
        """
        if not bot:
            bot = nonebot.get_bot()
        match superuser_id:
            case str(sid):
                superuser_ids = [sid]
            case _:
                if not (
                    superuser_ids := BotConfig.get_superuser(cls.get_platform(bot))
                ):
                    raise NotFindSuperuser()
        if isinstance(message, str):
            message = MessageUtils.build_message(message)
        result = []
        for sid in superuser_ids:
            try:
                result.append((sid, await cls.send_message(bot, sid, None, message)))
            except Exception as e:
                logger.error(
                    "发送消息给超级用户失败",
                    command="PlatformUtils:send_superuser",
                    target=sid,
                    e=e,
                )
        return result

    @classmethod
    async def send_message(
        cls,
        bot: Bot,
        user_id: str | None,
        group_id: str | None,
        message: str | UniMessage,
    ) -> Receipt | None:
        """发送消息

        参数:
            bot: Bot
            user_id: 用户id
            group_id: 群组id或频道id
            message: 消息文本

        返回:
            Receipt | None: 是否发送成功
        """
        if not (target := cls.get_target(user_id=user_id, group_id=group_id)):
            return None
        send_message = (
            MessageUtils.build_message(message)
            if isinstance(message, str)
            else message
        )
        return await send_message.send(target=target, bot=bot)

    @classmethod
    def get_platform(cls, t: Bot | Uninfo) -> str:
        """获取平台

        参数:
            t: Bot | Uninfo

        返回:
            str: 平台标识
        """
        if isinstance(t, Bot):
            if interface := get_interface(t):
                return _normalize_platform(interface.basic_info()["scope"])
            return "unknown"
        return _normalize_platform(t.basic["scope"])

    @classmethod
    def is_forward_merge_supported(cls, t: Bot | Uninfo) -> bool:
        """是否支持转发消息

        参数:
            t: bot | Uninfo

        返回:
            bool: 是否支持转发消息
        """
        if isinstance(t, Uninfo):
            scope = t.basic["scope"]
        elif interface := get_interface(t):
            scope = interface.basic_info()["scope"]
        else:
            return False
        return scope == SupportScope.qq_client

    @classmethod
    def get_target(
        cls,
        *,
        user_id: str | None = None,
        group_id: str | None = None,
        channel_id: str | None = None,
    ) -> Target | None:
        """获取发送Target

        参数:
            user_id: 用户id
            group_id: 群组id
            channel_id: 频道id

        返回:
            Target | None: 对应平台Target
        """
        match (group_id, channel_id, user_id):
            case (str(), str(), _):
                return Target(channel_id, parent_id=group_id, channel=True)
            case (str(), None, _):
                return Target(group_id)
            case (None, None, str()):
                return Target(user_id, private=True)
            case _:
                return None
