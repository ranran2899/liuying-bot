"""wife插件数据库模型"""

from datetime import date, datetime
import random
from typing import ClassVar

from sqlalchemy import Boolean, Date, DateTime, Integer, String, func
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
    ) -> UserWifeRecord | None:
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
    ) -> UserWifeRecord:
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


class WifeImageRecord(Model):
    """wife图片记录模型"""

    __tablename__ = "wife_image_record"
    __table_args__: ClassVar[dict] = {
        "comment": "wife图片记录表，存储图片元数据信息"
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    wife_name: Mapped[str] = mapped_column(
        String(255), index=True, comment="wife名称"
    )
    image_id: Mapped[int] = mapped_column(Integer, comment="图片编号")
    file_path: Mapped[str] = mapped_column(String(500), comment="存储路径")
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, index=True, comment="是否已删除"
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间"
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )

    @classmethod
    async def get_next_image_id(cls, wife_name: str) -> int:
        """获取指定wife名称的下一个图片ID

        参数:
            wife_name: wife名称

        返回:
            int: 下一个可用的图片ID
        """
        result = await cls.filter(
            wife_name=wife_name, is_deleted=False
        ).aggregate(func.max(cls.image_id))
        return (result[0] or 0) + 1

    @classmethod
    async def get_all_images_by_wife(
        cls, wife_name: str
    ) -> list[WifeImageRecord]:
        """获取指定wife的所有图片记录

        参数:
            wife_name: wife名称

        返回:
            list[WifeImageRecord]: 图片记录列表
        """
        return await cls.filter(wife_name=wife_name, is_deleted=False).all()

    @classmethod
    async def get_all_images(cls) -> list[WifeImageRecord]:
        """获取所有图片记录

        返回:
            list[WifeImageRecord]: 图片记录列表
        """
        return await cls.filter(is_deleted=False).all()

    @classmethod
    async def get_random_image(cls) -> WifeImageRecord | None:
        """随机获取一张图片

        返回:
            WifeImageRecord | None: 随机图片记录，不存在返回None
        """
        images = await cls.filter(is_deleted=False).all()
        return random.choice(images) if images else None

    @classmethod
    async def soft_delete_all_by_wife(cls, wife_name: str) -> int:
        """软删除指定wife的所有图片记录

        参数:
            wife_name: wife名称

        返回:
            int: 删除的记录数量
        """
        return await cls.filter(
            wife_name=wife_name, is_deleted=False
        ).update(is_deleted=True)

    @classmethod
    async def delete_all(cls) -> int:
        """物理删除所有图片记录

        返回:
            int: 删除的记录数量
        """
        return await cls.filter().delete()
