"""用户人格选择数据模型

定义 UserPersonaSelection，存储每个用户当前激活的bot人格选择。
实现用户级人格切换：不同用户可同时使用不同人格，互不影响。
"""

from datetime import datetime
from typing import ClassVar

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class UserPersonaSelection(Model):
    """用户人格选择模型

    存储用户当前激活的bot人格名，每个用户独立维护人格选择。
    """

    __tablename__ = "ai_user_persona_selection"
    __table_args__: ClassVar[dict] = {
        "comment": "AI用户人格选择表，存储用户当前激活的bot人格",
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增ID"
    )
    """自增ID"""

    user_id: Mapped[str] = mapped_column(
        String(255), unique=True, comment="用户ID"
    )
    """用户ID"""

    persona_name: Mapped[str] = mapped_column(
        String(64), default="default", comment="当前激活的bot人格名"
    )
    """当前激活的bot人格名"""

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="更新时间"
    )
    """更新时间"""

    cache_type = "AI_PERSONA_SELECTION"
    """缓存类型"""

    cache_key_field = "user_id"
    """缓存键字段"""

    @classmethod
    def _run_script(cls):
        """数据库初始化脚本"""
        return []

    @classmethod
    async def get_persona_name(
        cls, user_id: str
    ) -> str | None:
        """获取用户当前激活的人格名

        参数:
            user_id: 用户ID

        返回:
            str | None: 人格名，未设置时返回None（由调用方回退到全局默认）
        """
        record = await cls.filter(user_id=user_id).first()
        return record.persona_name if record else None

    @classmethod
    async def set_persona_name(
        cls, user_id: str, persona_name: str
    ) -> "UserPersonaSelection":
        """设置用户当前激活的人格名

        参数:
            user_id: 用户ID
            persona_name: 人格名

        返回:
            UserPersonaSelection: 更新后的记录
        """
        record, _ = await cls.get_or_create(user_id=user_id)
        record.persona_name = persona_name
        record.updated_at = datetime.now()
        await record.save(
            update_fields=["persona_name", "updated_at"]
        )
        return record

    @classmethod
    async def clear_persona_name(
        cls, user_id: str
    ) -> bool:
        """清除用户的人格选择（回退到全局默认）

        参数:
            user_id: 用户ID

        返回:
            bool: 是否清除成功
        """
        record = await cls.filter(user_id=user_id).first()
        if record:
            await record.delete()
            return True
        return False
