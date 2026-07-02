"""对话记录数据模型

定义 ConversationRecord，存储每轮对话的完整记录。
每条记录绑定 persona_name，实现用户不同人格间对话历史隔离。
"""

from datetime import datetime
from typing import ClassVar

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model

_DEFAULT_PERSONA = "default"
"""默认人格名（未指定时回退）"""


class ConversationRecord(Model):
    """对话记录模型

    存储每轮对话的完整记录，包括用户消息和AI回复。
    通过 persona_name 字段实现不同人格的对话历史隔离。
    """

    __tablename__ = "ai_conversation_record"
    __table_args__: ClassVar[dict] = {
        "comment": "AI对话记录表，存储每轮对话的完整内容",
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
    """bot人格名（实现人设间对话历史隔离）"""

    bot_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="机器人ID"
    )
    """机器人ID"""

    platform: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="平台"
    )
    """平台"""

    role: Mapped[str] = mapped_column(
        String(32), comment="角色：user/assistant/system"
    )
    """角色：user/assistant/system"""

    content: Mapped[str] = mapped_column(Text, comment="消息内容")
    """消息内容"""

    tokens: Mapped[int] = mapped_column(
        Integer, default=0, comment="token消耗"
    )
    """token消耗"""

    metadata_json: Mapped[str] = mapped_column(
        Text, default="{}", comment="元信息JSON（贴纸/TTS/工具调用）"
    )
    """元信息JSON（贴纸/TTS/工具调用）"""

    create_time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间"
    )
    """创建时间"""

    cache_type = "AI_CONVERSATION"
    """缓存类型"""

    cache_key_field = ("user_id", "group_id", "persona_name")
    """缓存键字段"""

    @classmethod
    def _run_script(cls):
        """数据库初始化脚本

        为旧表补齐 persona_name 列，实现人设间对话记忆隔离。
        若列已存在，ADD COLUMN 会失败并被捕获回滚，安全幂等。
        """
        return [
            "ALTER TABLE ai_conversation_record "
            "ADD COLUMN persona_name VARCHAR(64) "
            "NOT NULL DEFAULT 'default';",
            "CREATE INDEX IF NOT EXISTS idx_ai_conv_user_group_persona "
            "ON ai_conversation_record (user_id, group_id, persona_name);",
        ]

    @classmethod
    async def get_history(
        cls,
        user_id: str,
        group_id: str | None = None,
        limit: int = 20,
        persona_name: str = _DEFAULT_PERSONA,
    ) -> list["ConversationRecord"]:
        """获取用户对话历史

        参数:
            user_id: 用户ID
            group_id: 群组ID，None为私聊
            limit: 获取条数
            persona_name: bot人格名，用于人设间数据隔离

        返回:
            list[ConversationRecord]: 对话记录列表（按时间正序）
        """
        query = cls.filter(
            user_id=user_id, persona_name=persona_name
        )
        if group_id:
            query = query.filter(group_id=group_id)
        return await query.order_by("create_time").limit(limit).all()

    @classmethod
    async def add_record(
        cls,
        user_id: str,
        role: str,
        content: str,
        group_id: str | None = None,
        bot_id: str | None = None,
        platform: str | None = None,
        tokens: int = 0,
        metadata_json: str = "{}",
        persona_name: str = _DEFAULT_PERSONA,
    ) -> "ConversationRecord":
        """添加对话记录

        参数:
            user_id: 用户ID
            role: 角色
            content: 内容
            group_id: 群组ID
            bot_id: 机器人ID
            platform: 平台
            tokens: token消耗
            metadata_json: 元信息JSON
            persona_name: bot人格名

        返回:
            ConversationRecord: 创建的记录
        """
        return await cls.create(
            user_id=user_id,
            role=role,
            content=content,
            group_id=group_id,
            bot_id=bot_id,
            platform=platform,
            tokens=tokens,
            metadata_json=metadata_json,
            persona_name=persona_name,
        )

    @classmethod
    async def clear_history(
        cls,
        user_id: str,
        group_id: str | None = None,
        persona_name: str = _DEFAULT_PERSONA,
    ) -> int:
        """清空用户对话历史

        参数:
            user_id: 用户ID
            group_id: 群组ID
            persona_name: bot人格名

        返回:
            int: 删除的记录数
        """
        query = cls.filter(
            user_id=user_id, persona_name=persona_name
        )
        if group_id:
            query = query.filter(group_id=group_id)
        return await query.delete()

    @classmethod
    async def clear_all_records(cls) -> int:
        """清空所有用户的对话记录（管理员操作）

        返回:
            int: 删除的记录数
        """
        return await cls.filter().delete()
