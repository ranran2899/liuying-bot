"""引用回复与@回复

跨楼回复时带引用消息段，多人混战时@回复对象。
"""

from typing import Any

from nonebot_plugin_alconna import At, Reply, Text

from liuying.utils.log import logger

from ..config import get_config


class ReplyFormatter:
    """回复格式化器

    构建引用回复与@回复的消息段列表。
    引用回复由 QUOTE_REPLY_ENABLED 控制，
    @回复由 AT_REPLY_ENABLED 控制。
    """

    def build_quote_reply(
        self, text: str, message_id: int
    ) -> list[Any]:
        """构建引用回复消息段

        跨楼回复时带引用消息段。开关关闭或无文本时降级
        为纯文本/空列表。

        参数:
            text: 回复文本
            message_id: 被引用的消息ID

        返回:
            list[Any]: 消息段列表（Reply + Text）
        """
        if not get_config("QUOTE_REPLY_ENABLED", True):
            return [Text(text)] if text else []
        if not text:
            return [Reply(str(message_id))]
        logger.debug(
            f"构建引用回复 msg_id={message_id}", command="AI"
        )
        return [Reply(str(message_id)), Text(text)]

    def build_at_reply(
        self, text: str, user_id: str
    ) -> list[Any]:
        """构建@回复消息段

        多人混战时@回复对象。开关关闭时降级为纯文本。

        参数:
            text: 回复文本
            user_id: 被@的用户ID

        返回:
            list[Any]: 消息段列表（At + Text）
        """
        if not get_config("AT_REPLY_ENABLED", True):
            return [Text(text)] if text else []
        segments: list[Any] = [At(flag="user", target=user_id)]
        if text:
            segments.append(Text(text))
        logger.debug(
            f"构建@回复 user={user_id}", command="AI"
        )
        return segments


reply_formatter = ReplyFormatter()
"""回复格式化器单例"""
