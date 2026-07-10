from datetime import datetime, timedelta
from typing import ClassVar

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class Statistics(Model):
    """插件调用统计数据模型"""

    __tablename__ = "statistics"
    __table_args__: ClassVar[dict] = {
        "comment": "插件调用统计数据表",
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增ID"
    )
    """自增id"""
    user_id: Mapped[str | None] = mapped_column(String(255), comment="用户ID")
    """用户id"""
    group_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="群组ID"
    )
    """群组id"""
    plugin_name: Mapped[str | None] = mapped_column(String(255), comment="插件名称")
    """插件名称"""
    create_time: Mapped[datetime | None] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间"
    )
    """添加日期"""
    bot_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="机器人ID"
    )
    """Bot Id"""

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
        plugin_name: str | None = None,
        bot_id: str | None = None,
        days: int | None = None,
    ):
        """构建统计查询条件。

        参数:
            user_id: 用户ID，为None时不限制
            group_id: 群组ID，为None时不限制
            plugin_name: 插件名称，为None时不限制
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
        if plugin_name:
            query = query.filter(plugin_name=plugin_name)
        if bot_id:
            query = query.filter(bot_id=bot_id)
        if days:
            query = query.where_gte("create_time", cls._calc_start_time(days))
        return query

    @classmethod
    async def get_records(
        cls,
        user_id: str | None = None,
        group_id: str | None = None,
        plugin_name: str | None = None,
        bot_id: str | None = None,
        days: int | None = None,
    ) -> list["Statistics"]:
        """根据条件查询统计记录。

        参数:
            user_id: 用户ID，为None时不限制
            group_id: 群组ID，为None时不限制
            plugin_name: 插件名称，为None时不限制
            bot_id: 机器人ID，为None时不限制
            days: 时间范围（天），查询近N天数据，为None时查询全部

        返回:
            list[Statistics]: 统计记录列表
        """
        return await cls._build_query(
            user_id, group_id, plugin_name, bot_id, days
        ).all()

    @classmethod
    async def get_plugin_usage_count(
        cls,
        user_id: str | None = None,
        group_id: str | None = None,
        plugin_name: str | None = None,
        bot_id: str | None = None,
        days: int | None = None,
        limit: int | None = None,
    ) -> list[tuple[str, int]]:
        """获取插件调用次数统计（按次数降序）。

        参数:
            user_id: 用户ID，为None时不限制
            group_id: 群组ID，为None时不限制
            plugin_name: 插件名称，为None时不限制
            bot_id: 机器人ID，为None时不限制
            days: 时间范围（天），统计近N天数据，为None时统计全部
            limit: 返回前N条记录，为None时返回全部

        返回:
            list[tuple[str, int]]: [(插件名称, 调用次数), ...] 按调用次数降序
        """
        count_col = func.count(cls.id).label("count")
        query = (
            cls._build_query(user_id, group_id, plugin_name, bot_id, days)
            .annotate(count=count_col)
            .group_by(cls.plugin_name)
            .order_by(count_col.desc())
        )
        if limit:
            query = query.limit(limit)
        rows = await query.values(cls.plugin_name, count_col).all()
        return [(row[0], row[1]) for row in rows]

    @classmethod
    async def count_records(
        cls,
        user_id: str | None = None,
        group_id: str | None = None,
        plugin_name: str | None = None,
        bot_id: str | None = None,
        days: int | None = None,
    ) -> int:
        """统计符合条件的记录数量。

        参数:
            user_id: 用户ID，为None时不限制
            group_id: 群组ID，为None时不限制
            plugin_name: 插件名称，为None时不限制
            bot_id: 机器人ID，为None时不限制
            days: 时间范围（天），统计近N天数据，为None时统计全部

        返回:
            int: 记录数量
        """
        return await cls._build_query(
            user_id, group_id, plugin_name, bot_id, days
        ).count()

    @classmethod
    async def bulk_add(cls, records: list["Statistics"]) -> int:
        """批量添加统计记录。

        参数:
            records: 统计记录实例列表

        返回:
            int: 成功添加的记录数量
        """
        if not records:
            return 0
        await cls.filter().bulk_create(records)
        return len(records)

    @classmethod
    def _run_script(cls):
        """数据库初始化脚本"""
        return [
            "ALTER TABLE statistics ADD bot_id Text DEFAULT '';",
        ]
