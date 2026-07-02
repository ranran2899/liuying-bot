"""用户画像数据模型

定义 UserPersonaProfile，存储LLM生成的用户画像描述。
"""

from datetime import datetime
from typing import ClassVar

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class UserPersonaProfile(Model):
    """用户画像模型

    存储LLM生成的用户画像描述。
    """

    __tablename__ = "ai_user_persona"
    __table_args__: ClassVar[dict] = {
        "comment": "AI用户画像表",
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增ID"
    )
    """自增ID"""

    user_id: Mapped[str] = mapped_column(
        String(255), unique=True, comment="用户ID"
    )
    """用户ID"""

    persona: Mapped[str] = mapped_column(
        Text, default="", comment="画像描述"
    )
    """画像描述"""

    structured_json: Mapped[str] = mapped_column(
        Text, default="{}", comment="结构化字段JSON"
    )
    """结构化字段JSON"""

    user_correction: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="用户更正（最高优先级）"
    )
    """用户更正（最高优先级）"""

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="更新时间"
    )
    """更新时间"""

    cache_type = "AI_PERSONA"
    """缓存类型"""

    cache_key_field = "user_id"
    """缓存键字段"""

    @classmethod
    def _run_script(cls):
        """数据库初始化脚本"""
        return []

    @classmethod
    async def get_persona(cls, user_id: str) -> str:
        """获取用户画像

        参数:
            user_id: 用户ID

        返回:
            str: 画像描述（用户更正优先，其次LLM生成），无则返回空串
        """
        profile = await cls.filter(user_id=user_id).first()
        if not profile:
            return ""
        if profile.user_correction:
            return profile.user_correction
        return profile.persona

    @classmethod
    async def update_persona(
        cls,
        user_id: str,
        persona: str,
        structured_json: str = "{}",
    ) -> "UserPersonaProfile":
        """更新用户画像

        参数:
            user_id: 用户ID
            persona: 画像描述
            structured_json: 结构化字段JSON

        返回:
            UserPersonaProfile: 更新后的画像
        """
        profile, _ = await cls.get_or_create(user_id=user_id)
        profile.persona = persona
        profile.structured_json = structured_json
        profile.updated_at = datetime.now()
        await profile.save(
            update_fields=["persona", "structured_json", "updated_at"]
        )
        return profile
