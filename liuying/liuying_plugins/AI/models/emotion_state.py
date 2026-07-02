"""情绪状态数据模型

定义 EmotionState，存储AI对用户的情绪状态（mood/energy/relation_warmth）。
每条状态绑定 persona_name，实现用户不同人格间情绪数据隔离。
"""

from datetime import datetime
import json
from typing import ClassVar

from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model

_DEFAULT_PERSONA = "default"
"""默认人格名（未指定时回退）"""


class EmotionState(Model):
    """情绪状态模型

    存储AI对用户的情绪状态（mood/energy/relation_warmth）。
    通过 persona_name 字段实现不同人格的情绪状态隔离。
    """

    __tablename__ = "ai_emotion_state"
    __table_args__: ClassVar[dict] = {
        "comment": "AI情绪状态表",
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

    persona_name: Mapped[str] = mapped_column(
        String(64),
        default=_DEFAULT_PERSONA,
        index=True,
        comment="bot人格名",
    )
    """bot人格名（实现人设间情绪状态隔离）"""

    mood: Mapped[str] = mapped_column(
        String(32), default="neutral", comment="心情"
    )
    """心情：happy/sad/neutral/excited/angry/calm"""

    energy: Mapped[float] = mapped_column(
        Float, default=0.7, comment="能量值"
    )
    """能量值（0-1）"""

    pending_thoughts: Mapped[str] = mapped_column(
        Text, default="[]", comment="待处理想法JSON数组"
    )
    """待处理想法JSON数组"""

    relation_warmth: Mapped[float] = mapped_column(
        Float, default=0.3, comment="关系温度"
    )
    """关系温度（0-1）"""

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="更新时间"
    )
    """更新时间"""

    cache_type = "AI_EMOTION"
    """缓存类型"""

    cache_key_field = ("user_id", "group_id", "persona_name")
    """缓存键字段"""

    @classmethod
    def _run_script(cls):
        """数据库初始化脚本

        为旧表补齐 persona_name 列，实现人设间情绪状态隔离。
        若列已存在，ADD COLUMN 会失败并被捕获回滚，安全幂等。
        """
        return [
            "ALTER TABLE ai_emotion_state "
            "ADD COLUMN persona_name VARCHAR(64) "
            "NOT NULL DEFAULT 'default';",
        ]

    @classmethod
    async def get_state(
        cls,
        user_id: str,
        group_id: str | None = None,
        persona_name: str = _DEFAULT_PERSONA,
    ) -> "EmotionState":
        """获取情绪状态

        参数:
            user_id: 用户ID
            group_id: 群组ID
            persona_name: bot人格名

        返回:
            EmotionState: 情绪状态（不存在时创建默认）
        """
        state, _ = await cls.get_or_create(
            user_id=user_id,
            group_id=group_id,
            persona_name=persona_name,
        )
        return state

    @classmethod
    async def update_state(
        cls,
        user_id: str,
        mood: str | None = None,
        energy: float | None = None,
        relation_warmth: float | None = None,
        pending_thoughts: list[str] | None = None,
        group_id: str | None = None,
        persona_name: str = _DEFAULT_PERSONA,
    ) -> "EmotionState":
        """更新情绪状态

        参数:
            user_id: 用户ID
            mood: 心情
            energy: 能量值
            relation_warmth: 关系温度
            pending_thoughts: 待处理想法
            group_id: 群组ID
            persona_name: bot人格名

        返回:
            EmotionState: 更新后的情绪状态
        """
        state = await cls.get_state(
            user_id, group_id, persona_name=persona_name
        )
        update_fields: list[str] = []
        if mood is not None:
            state.mood = mood
            update_fields.append("mood")
        if energy is not None:
            state.energy = energy
            update_fields.append("energy")
        if relation_warmth is not None:
            state.relation_warmth = relation_warmth
            update_fields.append("relation_warmth")
        if pending_thoughts is not None:
            state.pending_thoughts = json.dumps(
                pending_thoughts, ensure_ascii=False
            )
            update_fields.append("pending_thoughts")
        state.updated_at = datetime.now()
        update_fields.append("updated_at")
        await state.save(update_fields=update_fields)
        return state
