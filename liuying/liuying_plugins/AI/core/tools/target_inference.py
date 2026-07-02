"""目标推断

判断群消息的目标是否为bot自身：@mention / reply_sender /
reply_to_msg_id 三层优先级短路判定。
"""

from typing import Any

__all__ = [
    "TARGET_BOT",
    "TARGET_OTHERS",
    "TARGET_UNCLEAR",
    "infer_message_target",
]


TARGET_BOT = "TARGET_BOT"
"""目标为bot自身"""


TARGET_UNCLEAR = "TARGET_UNCLEAR"
"""目标不明确（广播/无明确目标）"""


TARGET_OTHERS = "TARGET_OTHERS"
"""目标为其他人"""


class MessageTargetInferer:
    """消息目标推断器

    判断群消息的目标是否为bot自身：@mention / reply_sender /
    reply_to_msg_id 三层优先级短路判定。
    """

    @staticmethod
    def _extract_mentioned_ids(
        message_segments: list[Any],
        *,
        bot_self_id: str,
    ) -> tuple[list[str], bool]:
        """从消息段中提取被@的用户ID列表

        参数:
            message_segments: 消息段列表
            bot_self_id: bot自身ID

        返回:
            tuple[list[str], bool]: (被@用户ID列表, 是否@了bot)
        """
        mentioned: list[str] = []
        is_at_bot = False
        self_id = str(bot_self_id or "")

        for seg in message_segments or []:
            # 兼容 dict 与 MessageSegment 对象两种形态
            if isinstance(seg, dict):
                seg_type = str(seg.get("type", "") or "").lower()
                data = seg.get("data") or {}
            else:
                seg_type = str(
                    getattr(seg, "type", "") or ""
                ).lower()
                data = getattr(seg, "data", None) or {}
                if not isinstance(data, dict):
                    data = {}
            if seg_type not in ("at", "mention"):
                continue
            user_id = str(
                data.get("user_id") or data.get("qq") or data.get("id") or ""
            )
            if not user_id:
                continue
            if user_id == self_id:
                is_at_bot = True
            else:
                mentioned.append(user_id)

        return mentioned, is_at_bot

    @staticmethod
    def _extract_reply_sender_id(reply: Any) -> str:
        """从reply对象中提取回复目标发送者ID

        参数:
            reply: reply对象

        返回:
            str: 发送者ID，空串表示无
        """
        if reply is None:
            return ""
        if isinstance(reply, dict):
            return str(
                reply.get("user_id")
                or reply.get("sender_id")
                or ""
            )
        return str(
            getattr(reply, "user_id", "")
            or getattr(reply, "sender_id", "")
            or ""
        )

    @staticmethod
    def _extract_reply_message_id(event: Any) -> str:
        """从事件中提取被回复消息ID

        参数:
            event: 消息事件

        返回:
            str: 消息ID，空串表示无
        """
        reply = getattr(event, "reply", None)
        if reply is not None:
            if isinstance(reply, dict):
                return str(reply.get("message_id") or "")
            return str(getattr(reply, "message_id", "") or "")

        return str(getattr(event, "reply_to_msg_id", "") or "")

    @staticmethod
    def infer_message_target(
        event: Any,
        *,
        bot_self_id: str,
        recent_bot_messages: list[dict[str, str]] | None = None,
        window: int = 5,
    ) -> str:
        """推断消息目标是否为bot自身

        三层优先级判定：
        1. @mention层：@了bot返回TARGET_BOT，@了其他人返回TARGET_OTHERS
        2. reply_sender层：回复的发送者是bot返回TARGET_BOT
        3. reply_to_msg_id层：在最近bot消息中匹配到返回TARGET_BOT

        参数:
            event: 消息事件
            bot_self_id: bot自身ID
            recent_bot_messages: 最近bot发送的消息列表（含message_id字段）
            window: 回看窗口大小

        返回:
            str: TARGET_BOT / TARGET_OTHERS / TARGET_UNCLEAR
        """
        message = getattr(event, "message", None) or []
        if hasattr(message, "segments"):
            message = message.segments
        if not isinstance(message, list):
            message = list(message) if message else []

        mentioned_ids, is_at_bot = _extract_mentioned_ids(
            message, bot_self_id=bot_self_id
        )

        if is_at_bot:
            return TARGET_BOT
        if mentioned_ids:
            return TARGET_OTHERS

        reply = getattr(event, "reply", None)
        reply_sender_id = _extract_reply_sender_id(reply)
        if reply_sender_id and reply_sender_id == str(bot_self_id):
            return TARGET_BOT

        reply_to_msg_id = _extract_reply_message_id(event)
        if reply_to_msg_id:
            recent = list(recent_bot_messages or [])[-max(1, int(window)):]
            for msg in recent:
                msg_id = str(msg.get("message_id", "") or "")
                if msg_id and msg_id == reply_to_msg_id:
                    return TARGET_BOT
            return TARGET_OTHERS

        return TARGET_UNCLEAR


# 向后兼容别名：保持模块级函数引用以兼容旧调用方
_extract_mentioned_ids = MessageTargetInferer._extract_mentioned_ids
_extract_reply_sender_id = MessageTargetInferer._extract_reply_sender_id
_extract_reply_message_id = MessageTargetInferer._extract_reply_message_id
infer_message_target = MessageTargetInferer.infer_message_target
