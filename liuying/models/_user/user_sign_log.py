"""用户签到日志模型"""

from collections import Counter
from datetime import datetime
from typing import ClassVar

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class UserSignLog(Model):
    """用户签到日志模型

    用于记录用户每日签到记录，支持按月统计签到次数
    """

    __tablename__ = "user_sign_log"
    __table_args__: ClassVar[dict[str, str]] = {
        "comment": "用户签到日志表，用于记录用户每日签到记录"
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    """自增id"""
    user_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="用户id"
    )
    """用户id"""
    sign_date: Mapped[datetime] = mapped_column(nullable=False, comment="签到日期")
    """签到日期"""
    year: Mapped[int] = mapped_column(nullable=False, comment="年份")
    """年份"""
    month: Mapped[int] = mapped_column(nullable=False, comment="月份")
    """月份"""
    create_time: Mapped[datetime] = mapped_column(
        default=datetime.now, comment="创建时间"
    )
    """创建时间"""

    @classmethod
    async def add_sign_log(cls, user_id: str, sign_date: datetime) -> bool:
        """添加签到记录

        参数:
            user_id: 用户ID
            sign_date: 签到日期

        返回:
            bool: 添加成功返回True
        """
        await cls.create(
            user_id=user_id,
            sign_date=sign_date,
            year=sign_date.year,
            month=sign_date.month,
            db_name="log_db",
        )
        return True

    @classmethod
    async def get_recent_six_months_data(cls, user_id: str) -> dict[str, list]:
        """获取用户最近6个月的签到统计数据

        单次范围查询取回签到记录后内存聚合，避免逐月发6次统计查询。

        参数:
            user_id: 用户ID

        返回:
            dict[str, list]: 包含月份标签列表和对应签到次数列表的字典
        """
        now = datetime.now()
        start_month = now.month - 5
        start_year = now.year
        while start_month <= 0:
            start_month += 12
            start_year -= 1

        logs = (
            await cls.filter(user_id=user_id)
            .where_gte("sign_date", datetime(start_year, start_month, 1))
            .only("sign_date")
            .using("log_db")
            .all()
        )
        counter = Counter((log.sign_date.year, log.sign_date.month) for log in logs)

        months: list[str] = []
        counts: list[int] = []
        year, month = start_year, start_month
        for _ in range(6):
            months.append(f"{month}月")
            counts.append(counter.get((year, month), 0))
            month += 1
            if month > 12:
                month = 1
                year += 1
        return {"months": months, "counts": counts}
