"""
待审核图片数据库模型
"""

from datetime import datetime
from hashlib import sha256
import json
from typing import Any, ClassVar

from sqlalchemy import DateTime, Index, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class PendingReviewImage(Model):
    """
    待审核图片模型

    用于存储用户上传的图片，等待管理员审核通过后再正式入库。
    """

    __tablename__ = "pending_review_image"
    __table_args__: ClassVar[tuple] = (
        Index("ix_pending_review_image_status", "status"),
        Index("ix_pending_review_image_uploader_status", "uploader_id", "status"),
        {"comment": "待审核图片存储表，用于存储用户上传的待审核图片"},
    )

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    filename: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True, comment="文件名"
    )
    original_filename: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="原始文件名"
    )
    content_type: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="MIME类型"
    )
    file_size: Mapped[int] = mapped_column(
        nullable=False, default=0, comment="文件大小(字节)"
    )
    file_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, comment="文件SHA256哈希，用于重复检测"
    )
    file_data: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False, comment="图片二进制数据"
    )
    uploader_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, comment="上传者用户id"
    )
    source: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, comment="图片来源，如user_upload/ai_temp"
    )
    category: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="图片分类"
    )
    tags: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="图片标签，JSON数组字符串"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="图片描述"
    )
    status: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        index=True,
        comment="审核状态：0待审核/1已通过/2已拒绝",
    )
    reviewer_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="审核者用户id"
    )
    review_comment: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="审核备注"
    )
    review_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="审核时间"
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间"
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        comment="更新时间",
    )

    STATUS_PENDING = 0
    """待审核状态"""
    STATUS_APPROVED = 1
    """已通过状态"""
    STATUS_REJECTED = 2
    """已拒绝状态"""

    @classmethod
    async def save_image(
        cls,
        filename: str,
        file_data: bytes,
        content_type: str | None = None,
        original_filename: str | None = None,
        uploader_id: str | None = None,
        description: str | None = None,
        source: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
    ) -> "PendingReviewImage":
        """
        保存待审核图片到数据库

        参数:
            filename: 存储的文件名
            file_data: 图片二进制数据
            content_type: MIME类型
            original_filename: 原始文件名
            uploader_id: 上传者用户id
            description: 图片描述
            source: 图片来源
            category: 图片分类
            tags: 图片标签列表

        返回:
            PendingReviewImage: 保存的待审核图片模型实例
        """
        file_hash = sha256(file_data).hexdigest()
        defaults = {
            "file_data": file_data,
            "content_type": content_type,
            "original_filename": original_filename,
            "file_size": len(file_data),
            "file_hash": file_hash,
            "uploader_id": uploader_id,
            "source": source,
            "category": category,
            "tags": json.dumps(tags, ensure_ascii=False) if tags else None,
            "description": description,
            "status": cls.STATUS_PENDING,
        }
        instance, _ = await cls.update_or_create(
            defaults=defaults,
            filename=filename,
            db_name="bed_layout_db",
        )
        return instance

    @classmethod
    async def get_by_id(
        cls, image_id: int, include_data: bool = False
    ) -> "PendingReviewImage | None":
        """
        根据id获取待审核图片

        参数:
            image_id: 图片id
            include_data: 是否包含二进制数据，默认不包含

        返回:
            PendingReviewImage | None: 待审核图片模型实例或None
        """
        query = cls.filter(id=image_id).using("bed_layout_db")
        if not include_data:
            query = query.defer("file_data")
        return await query.first()

    @classmethod
    async def get_by_filename(
        cls, filename: str, include_data: bool = False
    ) -> "PendingReviewImage | None":
        """
        根据文件名获取待审核图片

        参数:
            filename: 文件名
            include_data: 是否包含二进制数据，默认不包含

        返回:
            PendingReviewImage | None: 待审核图片模型实例或None
        """
        query = cls.filter(filename=filename).using("bed_layout_db")
        if not include_data:
            query = query.defer("file_data")
        return await query.first()

    @classmethod
    async def get_by_hash(cls, file_hash: str) -> "PendingReviewImage | None":
        """
        根据文件哈希获取待审核图片，用于重复检测

        参数:
            file_hash: 文件SHA256哈希值

        返回:
            PendingReviewImage | None: 已存在的待审核图片模型实例或None
        """
        return await cls.filter(file_hash=file_hash).using("bed_layout_db").first()

    @classmethod
    async def list_by_status(
        cls,
        status: int,
        category: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list["PendingReviewImage"]:
        """
        根据审核状态获取图片列表

        参数:
            status: 审核状态
            category: 图片分类，为None时不筛选分类
            limit: 返回数量限制
            offset: 偏移量

        返回:
            list[PendingReviewImage]: 待审核图片列表（不含二进制数据）
        """
        query = cls.filter(status=status).using("bed_layout_db")
        if category is not None:
            query = query.filter(category=category)
        return (
            await query.defer("file_data")
            .order_by("-create_time")
            .offset(offset)
            .limit(limit)
            .all()
        )

    @classmethod
    async def list_pending(
        cls,
        category: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list["PendingReviewImage"]:
        """
        获取待审核图片列表

        参数:
            category: 图片分类，为None时不筛选分类
            limit: 返回数量限制
            offset: 偏移量

        返回:
            list[PendingReviewImage]: 待审核图片列表（不含二进制数据）
        """
        return await cls.list_by_status(
            cls.STATUS_PENDING,
            category=category,
            limit=limit,
            offset=offset,
        )

    @classmethod
    async def approve(
        cls,
        image_id: int,
        reviewer_id: str | None = None,
        comment: str | None = None,
    ) -> "PendingReviewImage | None":
        """
        通过待审核图片

        参数:
            image_id: 图片id
            reviewer_id: 审核者用户id
            comment: 审核备注

        返回:
            PendingReviewImage | None: 更新后的模型实例，图片不存在返回None
        """
        image = await cls.get_by_id(image_id, include_data=False)
        if not image:
            return None
        image.status = cls.STATUS_APPROVED
        image.reviewer_id = reviewer_id
        image.review_comment = comment
        image.review_time = datetime.now()
        image.update_time = datetime.now()
        await image.save(db_name="bed_layout_db")
        return image

    @classmethod
    async def reject(
        cls,
        image_id: int,
        reviewer_id: str | None = None,
        comment: str | None = None,
    ) -> "PendingReviewImage | None":
        """
        拒绝待审核图片

        参数:
            image_id: 图片id
            reviewer_id: 审核者用户id
            comment: 审核备注

        返回:
            PendingReviewImage | None: 更新后的模型实例，图片不存在返回None
        """
        image = await cls.get_by_id(image_id, include_data=False)
        if not image:
            return None
        image.status = cls.STATUS_REJECTED
        image.reviewer_id = reviewer_id
        image.review_comment = comment
        image.review_time = datetime.now()
        image.update_time = datetime.now()
        await image.save(db_name="bed_layout_db")
        return image

    @classmethod
    async def delete_by_id(cls, image_id: int) -> bool:
        """
        根据id删除待审核图片

        参数:
            image_id: 图片id

        返回:
            bool: 删除成功返回True，图片不存在返回False
        """
        image = await cls.get_by_id(image_id, include_data=False)
        if image:
            await image.delete(db_name="bed_layout_db")
            return True
        return False

    @classmethod
    async def get_stats(cls) -> dict[str, Any]:
        """
        获取待审核图片统计信息

        返回:
            dict[str, Any]: 包含各状态数量、总大小等统计信息
        """
        images = await cls.filter().using("bed_layout_db").defer("file_data").all()

        total_size = sum(img.file_size for img in images)
        by_status: dict[int, int] = {}
        by_category: dict[str, int] = {}
        for img in images:
            status = img.status if img.status is not None else -1
            by_status[status] = by_status.get(status, 0) + 1
            category = img.category or "unknown"
            by_category[category] = by_category.get(category, 0) + 1

        return {
            "total_count": len(images),
            "total_size": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "pending_count": by_status.get(cls.STATUS_PENDING, 0),
            "approved_count": by_status.get(cls.STATUS_APPROVED, 0),
            "rejected_count": by_status.get(cls.STATUS_REJECTED, 0),
            "by_status": by_status,
            "by_category": by_category,
        }
