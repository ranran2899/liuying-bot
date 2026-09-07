"""表情包用户反馈数据模型

定义 StickerFeedback，存储用户对表情包的显式反馈
（点赞/点踩/评论），用于反馈学习与策展调优。
"""

from datetime import datetime
from typing import ClassVar

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class StickerFeedback(Model):
    """表情包用户反馈模型

    存储用户对表情包的显式反馈（点赞/点踩/评论），
    用于反馈学习与策展调优。
    """

    __tablename__ = "ai_sticker_feedback"
    __table_args__: ClassVar[dict] = {
        "comment": "AI表情包用户反馈表",
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
    """用户ID"""

    group_id: Mapped[str] = mapped_column(
        String(255), default="", comment="群组ID"
    )
    """群组ID"""

    feedback_type: Mapped[str] = mapped_column(
        String(32), default="like", comment="反馈类型"
    )
    """反馈类型（like/dislike/report/comment）"""

    comment: Mapped[str] = mapped_column(
        Text, default="", comment="评论内容"
    )
    """评论内容"""

    create_time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, index=True, comment="反馈时间"
    )
    """反馈时间"""

    @classmethod
    def _run_script(cls):
        """数据库初始化脚本"""
        return [
            "CREATE INDEX IF NOT EXISTS idx_ai_sticker_feedback_sticker "
            "ON ai_sticker_feedback (sticker_id, feedback_type)",
            "CREATE INDEX IF NOT EXISTS idx_ai_sticker_feedback_user "
            "ON ai_sticker_feedback (user_id, feedback_type)",
        ]

    @classmethod
    async def add_feedback(
        cls,
        sticker_id: int,
        user_id: str = "",
        group_id: str = "",
        feedback_type: str = "like",
        comment: str = "",
    ) -> "StickerFeedback":
        """添加反馈

        参数:
            sticker_id: 表情包ID
            user_id: 用户ID
            group_id: 群组ID
            feedback_type: 反馈类型
            comment: 评论内容

        返回:
            StickerFeedback: 创建的反馈
        """
        return await cls.create(
            sticker_id=sticker_id,
            user_id=user_id,
            group_id=group_id,
            feedback_type=feedback_type,
            comment=comment[:500],
        )
