"""表情包使用记录数据模型

定义 StickerUsage，记录每次表情包发送的上下文，
用于反馈学习与策展。
"""

from datetime import datetime
import json
from typing import Any, ClassVar

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class StickerUsage(Model):
    """表情包使用记录模型

    记录每次表情包发送的上下文，用于反馈学习与策展。
    """

    __tablename__ = "ai_sticker_usage"
    __table_args__: ClassVar[dict] = {
        "comment": "AI表情包使用记录表",
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增ID"
    )
    """自增ID"""

    sticker_id: Mapped[int] = mapped_column(
        Integer, index=True, comment="表情包ID"
    )
    """表情包ID"""

    user_id: Mapped[str] = mapped_column(
        String(255), default="", index=True, comment="用户ID"
    )
    """用户ID（接收方）"""

    group_id: Mapped[str] = mapped_column(
        String(255), default="", index=True, comment="群组ID"
    )
    """群组ID"""

    bot_id: Mapped[str] = mapped_column(
        String(255), default="", comment="机器人ID"
    )
    """机器人ID"""

    context_text: Mapped[str] = mapped_column(
        Text, default="", comment="触发文本（回复正文）"
    )
    """触发文本（回复正文）"""

    detected_mood: Mapped[str] = mapped_column(
        String(32), default="", comment="检测到的情绪"
    )
    """检测到的情绪"""

    persona_mood: Mapped[str] = mapped_column(
        String(32), default="", comment="人格情绪"
    )
    """人格情绪"""

    reaction: Mapped[str] = mapped_column(
        String(32), default="unknown", comment="用户反应"
    )
    """用户反应（positive/negative/neutral/unknown）"""

    sent_time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, index=True, comment="发送时间"
    )
    """发送时间"""

    extra: Mapped[str] = mapped_column(
        Text, default="{}", comment="额外信息JSON"
    )
    """额外信息JSON"""

    @classmethod
    def _run_script(cls):
        """数据库初始化脚本"""
        return [
            "CREATE INDEX IF NOT EXISTS idx_ai_sticker_usage_sticker_time "
            "ON ai_sticker_usage (sticker_id, sent_time)",
            "CREATE INDEX IF NOT EXISTS idx_ai_sticker_usage_group_time "
            "ON ai_sticker_usage (group_id, sent_time)",
        ]

    @classmethod
    async def add_record(
        cls,
        sticker_id: int,
        user_id: str = "",
        group_id: str = "",
        bot_id: str = "",
        context_text: str = "",
        detected_mood: str = "",
        persona_mood: str = "",
        reaction: str = "unknown",
        extra: dict[str, Any] | None = None,
    ) -> "StickerUsage":
        """添加使用记录

        参数:
            sticker_id: 表情包ID
            user_id: 用户ID
            group_id: 群组ID
            bot_id: 机器人ID
            context_text: 触发文本
            detected_mood: 检测到的情绪
            persona_mood: 人格情绪
            reaction: 用户反应
            extra: 额外信息

        返回:
            StickerUsage: 创建的记录
        """
        return await cls.create(
            sticker_id=sticker_id,
            user_id=user_id,
            group_id=group_id,
            bot_id=bot_id,
            context_text=context_text[:500],
            detected_mood=detected_mood,
            persona_mood=persona_mood,
            reaction=reaction,
            extra=json.dumps(extra or {}, ensure_ascii=False),
        )

    @classmethod
    async def update_reaction(
        cls, record_id: int, reaction: str
    ) -> None:
        """更新用户反应

        参数:
            record_id: 记录ID
            reaction: 用户反应（positive/negative/neutral）
        """
        record = await cls.filter(id=record_id).first()
        if not record:
            return
        record.reaction = reaction
        await record.save(update_fields=["reaction"])
