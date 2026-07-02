"""
床图图片数据库模型
"""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, ClassVar

from sqlalchemy import Column, DateTime, Index, Integer, LargeBinary, String, Text

from liuying.services.liuying_db import Model


class BedLayoutImage(Model):
    """
    床图图片模型

    用于存储图片的二进制数据及相关元信息
    """

    __tablename__ = "bed_layout_image"
    __table_args__: ClassVar[tuple] = (
        Index("ix_bed_layout_image_source_category", "source", "category"),
        {"comment": "床图图片存储表，用于存储图片二进制数据"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="自增id")
    filename = Column(
        String(255), nullable=False, unique=True, index=True, comment="文件名"
    )
    original_filename = Column(String(255), nullable=True, comment="原始文件名")
    content_type = Column(String(100), nullable=True, comment="MIME类型")
    file_size = Column(Integer, nullable=False, default=0, comment="文件大小(字节)")
    file_hash = Column(
        String(64), nullable=True, index=True, comment="文件SHA256哈希，用于重复检测"
    )
    file_data = Column(LargeBinary, nullable=False, comment="图片二进制数据")
    source = Column(
        String(64), nullable=True, index=True, comment="图片来源，如ai_sticker/ai_temp"
    )
    category = Column(String(64), nullable=True, comment="图片分类")
    tags = Column(Text, nullable=True, comment="图片标签，JSON数组字符串")
    original_url = Column(Text, nullable=True, comment="原始图片URL")
    description = Column(Text, nullable=True, comment="图片描述")
    create_time = Column(DateTime, default=datetime.now, comment="创建时间")
    update_time = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )

    @classmethod
    async def save_image(
        cls,
        filename: str,
        file_data: bytes,
        content_type: str | None = None,
        original_filename: str | None = None,
        description: str | None = None,
        source: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        original_url: str | None = None,
    ) -> "BedLayoutImage":
        """
        保存图片到数据库

        参数:
            filename: 存储的文件名
            file_data: 图片二进制数据
            content_type: MIME类型
            original_filename: 原始文件名
            description: 图片描述
            source: 图片来源
            category: 图片分类
            tags: 图片标签列表
            original_url: 原始图片URL

        返回:
            BedLayoutImage: 保存的图片模型实例
        """
        file_hash = sha256(file_data).hexdigest()
        defaults = {
            "file_data": file_data,
            "content_type": content_type,
            "original_filename": original_filename,
            "file_size": len(file_data),
            "file_hash": file_hash,
            "source": source,
            "category": category,
            "tags": json.dumps(tags, ensure_ascii=False) if tags else None,
            "original_url": original_url,
            "description": description,
        }
        instance, _ = await cls.update_or_create(
            defaults=defaults,
            filename=filename,
            db_name="bed_layout_db",
        )
        return instance

    @classmethod
    async def get_image_by_filename(cls, filename: str) -> "BedLayoutImage | None":
        """
        根据文件名获取图片

        参数:
            filename: 文件名

        返回:
            BedLayoutImage | None: 图片模型实例或None
        """
        return await cls.filter(filename=filename).using("bed_layout_db").first()

    @classmethod
    async def get_image_by_hash(cls, file_hash: str) -> "BedLayoutImage | None":
        """
        根据文件哈希获取图片，用于重复检测

        参数:
            file_hash: 文件SHA256哈希值

        返回:
            BedLayoutImage | None: 已存在的图片模型实例或None
        """
        return await cls.filter(file_hash=file_hash).using("bed_layout_db").first()

    @classmethod
    async def get_images_by_source(
        cls,
        source: str,
        category: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list["BedLayoutImage"]:
        """
        根据来源和可选分类获取图片列表（不含二进制数据）

        参数:
            source: 图片来源
            category: 图片分类，为None时不筛选分类
            limit: 返回数量限制
            offset: 偏移量

        返回:
            list[BedLayoutImage]: 图片列表
        """
        query = cls.filter(source=source).using("bed_layout_db")
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
    async def delete_image_by_filename(cls, filename: str) -> bool:
        """
        根据文件名删除图片

        参数:
            filename: 文件名

        返回:
            bool: 删除成功返回True，图片不存在返回False
        """
        image = await cls.get_image_by_filename(filename)
        if image:
            await image.delete(db_name="bed_layout_db")
            return True
        return False

    @classmethod
    async def get_all_images(
        cls, limit: int = 100, offset: int = 0
    ) -> list["BedLayoutImage"]:
        """
        获取所有图片列表（不含二进制数据）

        参数:
            limit: 返回数量限制
            offset: 偏移量

        返回:
            list[BedLayoutImage]: 图片列表
        """
        return (
            await cls.filter()
            .using("bed_layout_db")
            .offset(offset)
            .limit(limit)
            .all()
        )

    @classmethod
    async def get_image_count(cls) -> int:
        """
        获取图片总数

        返回:
            int: 图片总数
        """
        return await cls.filter().using("bed_layout_db").count()

    @classmethod
    async def get_total_size(cls) -> int:
        """
        获取所有图片的总大小（使用聚合查询优化性能）

        返回:
            int: 总大小（字节）
        """
        try:
            return await cls.filter().using("bed_layout_db").sum("file_size")
        except Exception:
            images = await cls.filter().using("bed_layout_db").all()
            return sum(img.file_size for img in images)

    @classmethod
    async def get_stats(cls) -> dict[str, Any]:
        """
        获取图库统计信息（延迟加载二进制字段以优化性能）

        返回:
            dict[str, Any]: 包含图片总数、总大小及分类统计的字典，
                键为 image_count/total_size/total_size_mb/
                by_content_type/by_extension
        """
        images = await cls.filter().using("bed_layout_db").defer("file_data").all()

        image_count = len(images)
        total_size = sum(img.file_size for img in images)

        by_content_type: dict[str, int] = {}
        by_extension: dict[str, int] = {}
        by_source: dict[str, int] = {}
        by_category: dict[str, int] = {}
        for img in images:
            content_type = img.content_type or "unknown"
            by_content_type[content_type] = by_content_type.get(content_type, 0) + 1
            ext = (
                Path(img.filename).suffix.lower()
                if img.filename
                else "unknown"
            )
            by_extension[ext] = by_extension.get(ext, 0) + 1
            source = img.source or "unknown"
            by_source[source] = by_source.get(source, 0) + 1
            category = img.category or "unknown"
            by_category[category] = by_category.get(category, 0) + 1

        return {
            "image_count": image_count,
            "total_size": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "by_content_type": by_content_type,
            "by_extension": by_extension,
            "by_source": by_source,
            "by_category": by_category,
        }

    @classmethod
    async def search_by_name(
        cls, keyword: str, limit: int = 20
    ) -> list["BedLayoutImage"]:
        """
        按名称模糊搜索图片（同时匹配存储文件名与原始文件名）

        参数:
            keyword: 搜索关键词
            limit: 返回结果数量上限，默认20

        返回:
            list[BedLayoutImage]: 匹配的图片列表（不含二进制数据）
        """
        escaped = (
            keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        pattern = f"%{escaped}%"
        return (
            await cls.filter()
            .using("bed_layout_db")
            .where_or(
                ("filename", "ilike", pattern),
                ("original_filename", "ilike", pattern),
            )
            .defer("file_data")
            .order_by("-create_time")
            .limit(limit)
            .all()
        )

    @classmethod
    async def get_images_paginated(
        cls, page: int = 1, per_page: int = 20
    ) -> tuple[list["BedLayoutImage"], int, int]:
        """
        分页获取图片列表（不含二进制数据，按创建时间倒序）

        参数:
            page: 页码，从1开始
            per_page: 每页数量

        返回:
            tuple[list[BedLayoutImage], int, int]:
                当前页图片列表、总页数、图片总数
        """
        total = await cls.filter().using("bed_layout_db").count()
        total_pages = (total + per_page - 1) // per_page if total else 0
        page = max(1, min(page, total_pages)) if total_pages else 1
        offset = (page - 1) * per_page

        images = (
            await cls.filter()
            .using("bed_layout_db")
            .defer("file_data")
            .order_by("-create_time")
            .offset(offset)
            .limit(per_page)
            .all()
        )
        return images, total_pages, total

    # @classmethod
    # async def _run_script(cls) -> list[str]:
    #     """
    #     数据库迁移脚本：为 bed_layout_image 表增加 AI 插件所需的扩展字段

    #     在 bed_layout_db 数据库中按需添加 file_hash/source/category/tags/
    #     original_url 字段及复合索引，已存在时自动忽略错误。

    #     返回:
    #         list[str]: 空列表，实际迁移由方法内部直接执行
    #     """
    #     db_name = "bed_layout_db"
    #     try:
    #         session_manager = get_session(db_name)
    #     except RuntimeError:
    #         return []

    #     add_column_sqls = [
    #         "ALTER TABLE bed_layout_image ADD COLUMN file_hash VARCHAR(64)",
    #         "ALTER TABLE bed_layout_image ADD COLUMN source VARCHAR(64)",
    #         "ALTER TABLE bed_layout_image ADD COLUMN category VARCHAR(64)",
    #         "ALTER TABLE bed_layout_image ADD COLUMN tags TEXT",
    #         "ALTER TABLE bed_layout_image ADD COLUMN original_url TEXT",
    #     ]
    #     async with session_manager as session:
    #         for sql in add_column_sqls:
    #             try:
    #                 await session.execute(text(sql))
    #                 await session.commit()
    #             except Exception:
    #                 await session.rollback()
    #         try:
    #             await session.execute(
    #                 text(
    #                     "CREATE INDEX IF NOT EXISTS "
    #                     "ix_bed_layout_image_source_category "
    #                     "ON bed_layout_image(source, category)"
    #                 )
    #             )
    #             await session.commit()
    #         except Exception:
    #             await session.rollback()
    #     return []
