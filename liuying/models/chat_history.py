"""聊天历史记录模型"""

from datetime import datetime, timedelta
from typing import ClassVar

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


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
        String(255), nullable=True, comment="用户id"
    )
    """用户id"""
    group_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="群组id"
    )
    """群组id"""
    bot_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Bot ID"
    )
    """Bot ID"""
    message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="消息内容")
    """消息内容"""
    create_time: Mapped[datetime | None] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间"
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
    def _build_query(
        cls,
        user_id: str | None = None,
        group_id: str | None = None,
        bot_id: str | None = None,
        days: int | None = None,
    ):
        """构建聊天记录查询条件。

        参数:
            user_id: 用户ID，为None时不限制
            group_id: 群组ID，为None时不限制
            bot_id: 机器人ID，为None时不限制
            days: 时间范围（天），近N天数据，为None时不限制

        返回:
            QueryWrapper: 查询包装器
        """
        query = cls.filter()
        if user_id:
            query = query.filter(user_id=user_id)
        if group_id:
            query = query.filter(group_id=group_id)
        if bot_id:
            query = query.filter(bot_id=bot_id)
        if days:
            query = query.where_gte("create_time", cls._calc_start_time(days))
        return query

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
        return await cls._build_query(user_id, group_id, bot_id, days).count()

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
        count_col = func.count(cls.id).label("count")
        query = (
            cls._build_query(bot_id=bot_id, days=days)
            .filter(group_id__isnull=False)
            .annotate(count=count_col)
            .group_by(cls.group_id)
            .order_by(count_col.desc())
        )
        if limit:
            query = query.limit(limit)
        rows = await query.values(cls.group_id, count_col).all()
        return [(row[0], row[1]) for row in rows]
