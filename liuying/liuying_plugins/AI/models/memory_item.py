"""记忆项数据模型

定义 MemoryItem，存储4层记忆：working/episodic/semantic/background。
每条记忆绑定 persona_name，实现用户不同人格间记忆数据隔离。
"""

from datetime import datetime, timedelta
import json
from typing import ClassVar

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model

_DEFAULT_PERSONA = "default"
"""默认人格名（未指定时回退）"""


class MemoryItem(Model):
    """记忆项模型

    存储4层记忆：working/episodic/semantic/background。
    通过 persona_name 字段实现不同人格的记忆数据隔离。
    """

    __tablename__ = "ai_memory_item"
    __table_args__: ClassVar[dict] = {
        "comment": "AI记忆项表，存储4层记忆及元信息",
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
    """bot人格名（实现人设间记忆数据隔离）"""

    tier: Mapped[str] = mapped_column(
        String(32), default="working", comment="记忆层级"
    )
    """记忆层级：working/episodic/semantic/background"""

    summary: Mapped[str] = mapped_column(Text, comment="记忆摘要")
    """记忆摘要"""

    content: Mapped[str] = mapped_column(Text, comment="原始内容")
    """原始内容"""

    topic_tags: Mapped[str] = mapped_column(
        Text, default="[]", comment="话题标签JSON数组"
    )
    """话题标签JSON数组"""

    entity_tags: Mapped[str] = mapped_column(
        Text, default="[]", comment="实体标签JSON数组"
    )
    """实体标签JSON数组"""

    salience: Mapped[float] = mapped_column(
        Float, default=0.5, comment="重要性"
    )
    """重要性（0-1）"""

    stability: Mapped[float] = mapped_column(
        Float, default=0.5, comment="稳定性"
    )
    """稳定性（0-1）"""

    confidence: Mapped[float] = mapped_column(
        Float, default=0.5, comment="置信度"
    )
    """置信度（0-1）"""

    reinforcement_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="巩固次数"
    )
    """巩固次数"""

    access_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="访问次数"
    )
    """访问次数"""

    last_access_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="最后访问时间"
    )
    """最后访问时间"""

    create_time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间"
    )
    """创建时间"""

    expire_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="过期时间"
    )
    """过期时间（working层24h）"""

    superseded_by: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="被哪条记忆覆盖"
    )
    """被哪条记忆覆盖"""

    is_protected: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否受保护"
    )
    """是否受保护（semantic/background）"""

    cache_type = "AI_MEMORY"
    """缓存类型"""

    cache_key_field = "id"
    """缓存键字段"""

    @classmethod
    def _run_script(cls):
        """数据库初始化脚本

        为旧表补齐 persona_name 列，实现人设间记忆隔离。
        若列已存在，ADD COLUMN 会失败并被捕获回滚，安全幂等。
        """
        return [
            "ALTER TABLE ai_memory_item "
            "ADD COLUMN persona_name VARCHAR(64) "
            "NOT NULL DEFAULT 'default';",
            "CREATE INDEX IF NOT EXISTS idx_ai_memory_user_persona "
            "ON ai_memory_item (user_id, persona_name);",
        ]

    @classmethod
    async def add_memory(
        cls,
        user_id: str,
        content: str,
        summary: str | None = None,
        group_id: str | None = None,
        tier: str = "working",
        topic_tags: list[str] | None = None,
        entity_tags: list[str] | None = None,
        salience: float = 0.5,
        is_protected: bool = False,
        persona_name: str = _DEFAULT_PERSONA,
    ) -> "MemoryItem":
        """添加记忆项

        参数:
            user_id: 用户ID
            content: 原始内容
            summary: 摘要，None时用content
            group_id: 群组ID
            tier: 记忆层级
            topic_tags: 话题标签
            entity_tags: 实体标签
            salience: 重要性
            is_protected: 是否受保护
            persona_name: bot人格名

        返回:
            MemoryItem: 创建的记忆项
        """
        expire_time = None
        if tier == "working":
            expire_time = datetime.now() + timedelta(hours=24)

        return await cls.create(
            user_id=user_id,
            content=content,
            summary=summary or content,
            group_id=group_id,
            persona_name=persona_name,
            tier=tier,
            topic_tags=json.dumps(topic_tags or [], ensure_ascii=False),
            entity_tags=json.dumps(entity_tags or [], ensure_ascii=False),
            salience=salience,
            is_protected=is_protected or tier in ("semantic", "background"),
            expire_time=expire_time,
        )

    @classmethod
    async def clear_by_user_persona(
        cls,
        user_id: str,
        persona_name: str = _DEFAULT_PERSONA,
        group_id: str | None = None,
    ) -> list[int]:
        """清空指定用户指定人格的记忆（返回被删除的记忆ID列表）

        参数:
            user_id: 用户ID
            persona_name: bot人格名
            group_id: 群组ID，None时清除所有群组

        返回:
            list[int]: 被删除的记忆ID列表（供调用方清理搜索索引）
        """
        query = cls.filter(
            user_id=user_id, persona_name=persona_name
        )
        if group_id:
            query = query.filter(group_id=group_id)
        memories = await query.all()
        if not memories:
            return []
        ids = [m.id for m in memories]
        await cls.filter(id__in=ids).delete()
        return ids

    @classmethod
    async def clear_all_memories(cls) -> list[int]:
        """清空所有记忆（管理员操作，返回被删除的记忆ID列表）

        返回:
            list[int]: 被删除的记忆ID列表（供调用方清理搜索索引）
        """
        memories = await cls.filter().all()
        if not memories:
            return []
        ids = [m.id for m in memories]
        await cls.filter(id__in=ids).delete()
        return ids
