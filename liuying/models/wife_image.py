"""wife图片记录数据库模型"""

from datetime import datetime
import random
from typing import ClassVar

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


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
    original_filename: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="原始文件名"
    )
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
    async def create_image_record(
        cls,
        wife_name: str,
        image_id: int,
        file_path: str,
        original_filename: str | None = None,
    ) -> "WifeImageRecord":
        """创建图片记录

        参数:
            wife_name: wife名称
            image_id: 图片编号
            file_path: 存储路径
            original_filename: 原始文件名

        返回:
            WifeImageRecord: 创建的记录
        """
        return await cls.create(
            wife_name=wife_name,
            image_id=image_id,
            file_path=file_path,
            original_filename=original_filename,
        )

    @classmethod
    async def get_image_by_id(
        cls, wife_name: str, image_id: int
    ) -> "WifeImageRecord | None":
        """根据wife名称和图片ID获取图片记录

        参数:
            wife_name: wife名称
            image_id: 图片编号

        返回:
            WifeImageRecord | None: 图片记录，不存在返回None
        """
        return await cls.safe_get_or_none(
            wife_name=wife_name, image_id=image_id, is_deleted=False
        )

    @classmethod
    async def get_all_images_by_wife(
        cls, wife_name: str
    ) -> list["WifeImageRecord"]:
        """获取指定wife的所有图片记录

        参数:
            wife_name: wife名称

        返回:
            list[WifeImageRecord]: 图片记录列表
        """
        return await cls.filter(wife_name=wife_name, is_deleted=False).all()

    @classmethod
    async def get_all_images(cls) -> list["WifeImageRecord"]:
        """获取所有图片记录

        返回:
            list[WifeImageRecord]: 图片记录列表
        """
        return await cls.filter(is_deleted=False).all()

    @classmethod
    async def soft_delete_image(cls, wife_name: str, image_id: int) -> bool:
        """软删除图片记录

        参数:
            wife_name: wife名称
            image_id: 图片编号

        返回:
            bool: 删除成功返回True
        """
        image = await cls.get_image_by_id(wife_name, image_id)
        if image:
            image.is_deleted = True
            await image.save(update_fields=["is_deleted", "update_time"])
            return True
        return False

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
    async def hard_delete_all_deleted(cls) -> int:
        """物理删除所有已软删除的记录

        返回:
            int: 删除的记录数量
        """
        return await cls.filter(is_deleted=True).delete()

    @classmethod
    async def get_image_count_by_wife(cls, wife_name: str) -> int:
        """获取指定wife的图片数量

        参数:
            wife_name: wife名称

        返回:
            int: 图片数量
        """
        return await cls.filter(
            wife_name=wife_name, is_deleted=False
        ).count()

    @classmethod
    async def get_total_image_count(cls) -> int:
        """获取所有图片总数

        返回:
            int: 图片总数
        """
        return await cls.filter(is_deleted=False).count()

    @classmethod
    async def get_random_image(cls) -> "WifeImageRecord | None":
        """随机获取一张图片

        返回:
            WifeImageRecord | None: 随机图片记录，不存在返回None
        """
        images = await cls.filter(is_deleted=False).all()
        return random.choice(images) if images else None
