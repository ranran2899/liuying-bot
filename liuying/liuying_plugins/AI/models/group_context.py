"""群上下文快照数据模型

定义 GroupContextSnapshot，存储群风格、群摘要、活跃用户等信息。
"""

from datetime import datetime
import json
from typing import ClassVar

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class GroupContextSnapshot(Model):
    """群上下文快照模型

    存储群风格、群摘要、活跃用户等信息。
    """

    __tablename__ = "ai_group_context"
    __table_args__: ClassVar[dict] = {
        "comment": "AI群上下文快照表",
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增ID"
    )
    """自增ID"""

    group_id: Mapped[str] = mapped_column(
        String(255), index=True, comment="群组ID"
    )
    """群组ID"""

    style: Mapped[str] = mapped_column(
        Text, default="", comment="群风格描述"
    )
    """群风格描述"""

    summary: Mapped[str] = mapped_column(
        Text, default="", comment="群摘要"
    )
    """群摘要"""

    active_users: Mapped[str] = mapped_column(
        Text, default="[]", comment="活跃用户JSON数组"
    )
    """活跃用户JSON数组"""

    last_activity_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="最后活动时间"
    )
    """最后活动时间"""

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="群是否启用主动行为"
    )
    """群是否启用主动行为"""

    extra: Mapped[str] = mapped_column(
        Text, default="{}", comment="额外信息JSON"
    )
    """额外信息JSON（如社交数据/角色/关系等）"""

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="更新时间"
    )
    """更新时间"""

    cache_type = "AI_GROUP_CTX"
    """缓存类型"""

    cache_key_field = "group_id"
    """缓存键字段"""


    @classmethod
    async def get_context(cls, group_id: str) -> "GroupContextSnapshot | None":
        """获取群上下文

        参数:
            group_id: 群组ID

        返回:
            GroupContextSnapshot | None: 群上下文快照
        """
        return await cls.filter(group_id=group_id).first()

    @classmethod
    async def update_context(
        cls,
        group_id: str,
        style: str | None = None,
        summary: str | None = None,
        active_users: list[str] | None = None,
        is_active: bool | None = None,
    ) -> "GroupContextSnapshot":
        """更新群上下文

        参数:
            group_id: 群组ID
            style: 群风格
            summary: 群摘要
            active_users: 活跃用户列表
            is_active: 是否启用主动行为

        返回:
            GroupContextSnapshot: 更新后的群上下文
        """
        ctx, _ = await cls.get_or_create(group_id=group_id)
        update_fields: list[str] = []
        if style is not None:
            ctx.style = style
            update_fields.append("style")
        if summary is not None:
            ctx.summary = summary
            update_fields.append("summary")
        if active_users is not None:
            ctx.active_users = json.dumps(
                active_users, ensure_ascii=False
            )
            update_fields.append("active_users")
        if is_active is not None:
            ctx.is_active = is_active
            update_fields.append("is_active")
        ctx.last_activity_time = datetime.now()
        ctx.updated_at = datetime.now()
        update_fields.extend(["last_activity_time", "updated_at"])
        await ctx.save(update_fields=update_fields)
        return ctx


    @classmethod
    def _run_script(cls):
        """数据库初始化脚本

        为旧表补齐 is_active、extra 列，兼容 SQLite/MySQL/PostgreSQL。
        若列已存在，ADD COLUMN 会失败并被 _run_script_methods 捕获回滚，安全幂等。
        """
        return [
            "ALTER TABLE ai_group_context ADD COLUMN is_active BOOLEAN DEFAULT TRUE;",
            "ALTER TABLE ai_group_context ADD COLUMN extra TEXT DEFAULT '{}';",
        ]
