"""用户wife记录数据库模型"""

from datetime import date
from typing import ClassVar

from sqlalchemy import Date, String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class UserWifeRecord(Model):
    """用户wife记录模型"""

    __tablename__ = "user_wife_record"
    __table_args__: ClassVar[dict] = {
        "comment": "用户wife记录表，存储用户每日抽取的wife信息"
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    user_id: Mapped[str] = mapped_column(
        String(255), index=True, comment="用户id"
    )
    wife_name: Mapped[str] = mapped_column(String(255), comment="wife名称")
    record_date: Mapped[date] = mapped_column(Date, comment="记录日期")

    @classmethod
    async def get_user_wife(
        cls, user_id: str, record_date: date
    ) -> "UserWifeRecord | None":
        """获取用户指定日期的wife记录

        参数:
            user_id: 用户ID
            record_date: 记录日期

        返回:
            UserWifeRecord | None: wife记录，不存在返回None
        """
        return await cls.safe_get_or_none(user_id=user_id, record_date=record_date)

    @classmethod
    async def set_user_wife(
        cls, user_id: str, wife_name: str, record_date: date
    ) -> "UserWifeRecord":
        """设置用户指定日期的wife记录

        参数:
            user_id: 用户ID
            wife_name: wife名称
            record_date: 记录日期

        返回:
            UserWifeRecord: 创建或更新的记录
        """
        record, _ = await cls.update_or_create(
            user_id=user_id,
            record_date=record_date,
            defaults={"wife_name": wife_name},
        )
        return record

    @classmethod
    async def get_today_count(cls, record_date: date) -> int:
        """获取指定日期的wife记录总数

        参数:
            record_date: 记录日期

        返回:
            int: 记录总数
        """
        return await cls.filter(record_date=record_date).count()

    @classmethod
    async def clear_all_records(cls) -> int:
        """清空所有wife记录

        返回:
            int: 删除的记录数量
        """
        return await cls.filter().delete()
