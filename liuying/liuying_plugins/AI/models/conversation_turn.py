"""对话轮次统计模型

定义 ConversationTurn，统计用户与AI的对话轮次和token消耗。
"""

from datetime import datetime
from typing import ClassVar

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class ConversationTurn(Model):
    """对话轮次统计模型

    统计用户与AI的对话轮次和token消耗。
    """

    __tablename__ = "ai_conversation_turn"
    __table_args__: ClassVar[dict] = {
        "comment": "AI对话轮次统计表",
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增ID"
    )
    """自增ID"""

    user_id: Mapped[str] = mapped_column(
        String(255), index=True, comment="用户ID"
    )
    """用户ID"""

    group_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True, comment="群组ID"
    )
    """群组ID"""

    turn_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="对话轮次"
    )
    """对话轮次"""

    last_turn_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="最后对话时间"
    )
    """最后对话时间"""

    total_tokens: Mapped[int] = mapped_column(
        Integer, default=0, comment="总token消耗"
    )
    """总token消耗"""

    cache_type = "AI_TURN"
    """缓存类型"""

    cache_key_field = ("user_id", "group_id")
    """缓存键字段"""

    @classmethod
    def _run_script(cls):
        """数据库初始化脚本"""
        return []

    @classmethod
    async def increment_turn(
        cls,
        user_id: str,
        tokens: int = 0,
        group_id: str | None = None,
    ) -> "ConversationTurn":
        """增加对话轮次

        参数:
            user_id: 用户ID
            tokens: 本轮token消耗
            group_id: 群组ID

        返回:
            ConversationTurn: 更新后的轮次记录
        """
        turn, _ = await cls.get_or_create(
            user_id=user_id,
            group_id=group_id,
        )
        turn.turn_count += 1
        turn.total_tokens += tokens
        turn.last_turn_time = datetime.now()
        await turn.save(
            update_fields=["turn_count", "total_tokens", "last_turn_time"]
        )
        return turn
