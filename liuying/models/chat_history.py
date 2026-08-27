"""聊天历史记录模型"""

from datetime import datetime, timedelta
from typing import ClassVar

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model

_MESSAGE_MAX_LENGTH = 5000


class ChatHistory(Model):
    """聊天历史记录模型类

    用于记录机器人接收到的消息历史
    """

    __tablename__ = "chat_history"
    __table_args__: ClassVar[dict] = {"comment": "聊天历史记录表"}

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    """自增id"""
    user_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True, comment="用户id"
    )
    """用户id"""
    group_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True, comment="群组id"
    )
    """群组id"""
    bot_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True, comment="Bot ID"
    )
    """Bot ID"""
    message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="消息内容")
    """消息内容"""
    create_time: Mapped[datetime | None] = mapped_column(
        DateTime, default=datetime.now, index=True, comment="创建时间"
    )
    """创建时间"""

    @staticmethod
    def _calc_start_time(days: int) -> datetime:
        """计算近N天的起始时间（对齐到自然日0点）。

        参数:
            days: 天数（1表示今天，7表示近7天）

        返回:
            datetime: 起始时间
        """
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return today - timedelta(days=days - 1)

    @classmethod
    async def add_record(
        cls,
        user_id: str | None = None,
        group_id: str | None = None,
        bot_id: str | None = None,
        message: str | None = None,
    ) -> "ChatHistory":
        """写入一条聊天记录。

        参数:
            user_id: 用户ID
            group_id: 群组ID
            bot_id: 机器人ID
            message: 消息内容

        返回:
            ChatHistory: 创建的记录实例
        """
        return await cls.create(
            user_id=user_id,
            group_id=group_id,
            bot_id=bot_id,
            message=message[:_MESSAGE_MAX_LENGTH] if message else None,
        )

    @classmethod
    async def bulk_add(cls, records: list["ChatHistory"]) -> int:
        """批量写入聊天记录。

        参数:
            records: 聊天记录实例列表

        返回:
            int: 成功写入的记录数量
        """
        if not records:
            return 0
        await cls.filter().bulk_create(records)
        return len(records)

    @classmethod
    async def count_records(
        cls,
        user_id: str | None = None,
        group_id: str | None = None,
        bot_id: str | None = None,
        days: int | None = None,
    ) -> int:
        """统计符合条件的聊天记录数量。

        参数:
            user_id: 用户ID，为None时不限制
            group_id: 群组ID，为None时不限制
            bot_id: 机器人ID，为None时不限制
            days: 时间范围（天），统计近N天数据，为None时统计全部

        返回:
            int: 记录数量
        """
        return await cls.filter(
            skip_none=True,
            user_id=user_id,
            group_id=group_id,
            bot_id=bot_id,
            create_time__gte=cls._calc_start_time(days) if days else None,
        ).count()

    @classmethod
    async def get_active_groups(
        cls,
        bot_id: str | None = None,
        days: int | None = None,
        limit: int | None = None,
    ) -> list[tuple[str, int]]:
        """获取活跃群组（按消息数降序）。

        参数:
            bot_id: 机器人ID，为None时不限制
            days: 时间范围（天），统计近N天数据，为None时统计全部
            limit: 返回前N条记录，为None时返回全部

        返回:
            list[tuple[str, int]]: [(群组ID, 消息数), ...] 按消息数降序
        """
        return await cls.filter(
            skip_none=True,
            bot_id=bot_id,
            group_id__isnull=False,
            create_time__gte=cls._calc_start_time(days) if days else None,
        ).group_count(group_column="group_id", count_column="id", limit=limit)

    @classmethod
    def _run_script(cls):
        """数据库迁移脚本

        为旧库补齐消息列与高频查询字段的索引（新库由列定义自动创建），
        名称与 SQLAlchemy 自动生成的 ix_<table>_<column> 一致，幂等可重复执行。

        返回:
            list: SQL语句列表，用于数据库表结构更新
        """
        return [
            "ALTER TABLE chat_history ADD message TEXT;",
            "CREATE INDEX IF NOT EXISTS ix_chat_history_user_id "
            "ON chat_history (user_id);",
            "CREATE INDEX IF NOT EXISTS ix_chat_history_group_id "
            "ON chat_history (group_id);",
            "CREATE INDEX IF NOT EXISTS ix_chat_history_bot_id "
            "ON chat_history (bot_id);",
            "CREATE INDEX IF NOT EXISTS ix_chat_history_create_time "
            "ON chat_history (create_time);",
        ]
