"""消息目标推断

在群聊中判断消息的目标是bot、他人还是不明确。
用于避免误回复@他人的消息，提升群聊精准回复能力。

判断逻辑：
1. 检查@bot → TARGET_BOT
2. 检查@他人 → TARGET_OTHERS
3. 检查回复bot的消息 → TARGET_BOT
4. 检查回复他人的消息 → TARGET_OTHERS
5. 都不匹配 → TARGET_UNCLEAR
"""

from enum import StrEnum
from typing import Any

__all__ = [
    "MessageTarget",
    "TargetInference",
    "target_inference",
]


class MessageTarget(StrEnum):
    """消息目标枚举"""

    BOT = "TARGET_BOT"
    """目标为bot"""
    OTHERS = "TARGET_OTHERS"
    """目标为他人"""
    UNCLEAR = "TARGET_UNCLEAR"
    """目标不明确"""


class TargetInference:
    """消息目标推断器

    封装群聊消息目标判断逻辑。所有方法均为静态方法，
    可直接通过类名调用。

    支持多种协议适配器（OneBot V11/V12、QQ官方适配器），
    通过遍历 message segments 提取@和回复信息。
    """

    @staticmethod
    def _extract_at_ids(
        message: Any,
    ) -> tuple[list[str], bool]:
        """从消息中提取被@的用户ID列表

        参数:
            message: 消息对象（支持遍历segments）

        返回:
            tuple[list[str], bool]: (被@的ID列表, 是否@了bot)
        """
        at_ids: list[str] = []
        is_at_bot = False
        if message is None:
            return at_ids, is_at_bot
        try:
            for seg in message:
                seg_type = getattr(seg, "type", "") or ""
                if seg_type in ("at", "mention_user", "mention"):
                    data = (
                        seg.data
                        if hasattr(seg, "data")
                        else {}
                    )
                    if isinstance(data, dict):
                        user_id = str(
                            data.get("qq")
                            or data.get("user_id")
                            or data.get("target_id")
                            or ""
                        )
                    else:
                        user_id = str(
                            getattr(data, "qq", None)
                            or getattr(data, "user_id", None)
                            or getattr(
                                data, "target_id", None
                            )
                            or ""
                        )
                    if user_id:
                        at_ids.append(user_id)
        except Exception:
            pass
        return at_ids, is_at_bot

    @staticmethod
    def _extract_reply_sender_id(
        reply: Any,
    ) -> str:
        """从回复消息中提取原消息发送者ID

        参数:
            reply: 回复消息对象

        返回:
            str: 原消息发送者ID，无回复返回空串
        """
        if reply is None:
            return ""
        try:
            sender = getattr(reply, "sender", None)
            if sender is not None:
                user_id = (
                    getattr(sender, "user_id", None)
                    or getattr(sender, "id", None)
                )
                if user_id:
                    return str(user_id)
            user_id = (
                getattr(reply, "user_id", None)
                or getattr(reply, "sender_id", None)
            )
            if user_id:
                return str(user_id)
        except Exception:
            pass
        return ""

    @staticmethod
    def infer_message_target(
        event: Any,
        *,
        bot_self_id: str,
    ) -> MessageTarget:
        """推断群聊消息的目标

        参数:
            event: 消息事件
            bot_self_id: bot自身ID

        返回:
            MessageTarget: 消息目标枚举
        """
        self_id = str(bot_self_id or "").strip()
        if not self_id:
            return MessageTarget.UNCLEAR

        at_ids, _ = TargetInference._extract_at_ids(
            getattr(event, "message", None)
        )
        if at_ids:
            if self_id in at_ids:
                return MessageTarget.BOT
            return MessageTarget.OTHERS

        reply = getattr(event, "reply", None)
        if reply is not None:
            reply_sender = (
                TargetInference._extract_reply_sender_id(reply)
            )
            if reply_sender:
                if reply_sender == self_id:
                    return MessageTarget.BOT
                return MessageTarget.OTHERS

        return MessageTarget.UNCLEAR


target_inference = TargetInference()
"""消息目标推断器单例"""
