"""
漂流瓶数据库模型

包含漂流瓶记录、图片元数据、评论和点赞数据
"""
from datetime import datetime
from typing import ClassVar

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class BottleRecord(Model):
    """漂流瓶记录模型"""

    __tablename__ = "bottle_record"
    __table_args__: ClassVar[dict] = {
        "comment": "漂流瓶记录表，存储漂流瓶内容与状态"
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="漂流瓶ID"
    )
    content: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="瓶子文本内容"
    )
    user_id: Mapped[str] = mapped_column(
        String(255), index=True, comment="发送者用户ID"
    )
    group_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="发送群组ID"
    )
    platform: Mapped[str] = mapped_column(
        String(50), default="unknown", comment="发送平台"
    )
    status: Mapped[int] = mapped_column(
        Integer, default=0, index=True, comment="状态: 0待审核, 100已拒绝, 200已通过"
    )
    like_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="点赞数"
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间"
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )

    @classmethod
    async def create_bottle(
        cls,
        content: str | None,
        user_id: str,
        group_id: str | None = None,
        platform: str = "unknown",
    ) -> "BottleRecord":
        """
        创建漂流瓶记录

        参数:
            content: 文本内容
            user_id: 发送者用户ID
            group_id: 发送群组ID
            platform: 发送平台

        返回:
            BottleRecord: 创建的记录
        """
        return await cls.create(
            content=content,
            user_id=user_id,
            group_id=group_id,
            platform=platform,
            status=0,
        )

    @classmethod
    async def get_approved_by_id(
        cls, bottle_id: int
    ) -> "BottleRecord | None":
        """
        根据ID获取已通过审核的漂流瓶

        参数:
            bottle_id: 漂流瓶ID

        返回:
            BottleRecord | None: 漂流瓶记录，不存在返回None
        """
        return await cls.safe_get_or_none(id=bottle_id, status=200)

    @classmethod
    async def get_by_id(cls, bottle_id: int) -> "BottleRecord | None":
        """
        根据ID获取漂流瓶（任意状态）

        参数:
            bottle_id: 漂流瓶ID

        返回:
            BottleRecord | None: 漂流瓶记录，不存在返回None
        """
        return await cls.safe_get_or_none(id=bottle_id)

    @classmethod
    async def get_random_approved(cls) -> "BottleRecord | None":
        """
        随机获取一个已通过审核的漂流瓶

        返回:
            BottleRecord | None: 随机漂流瓶记录，不存在返回None
        """
        import random

        records = await cls.filter(status=200).all()
        if not records:
            return None
        return random.choice(records)

    @classmethod
    async def approve_bottle(cls, bottle_id: int) -> bool:
        """
        审核通过漂流瓶

        参数:
            bottle_id: 漂流瓶ID

        返回:
            bool: 操作成功返回True
        """
        record = await cls.get_by_id(bottle_id)
        if not record:
            return False
        record.status = 200
        await record.save(update_fields=["status", "update_time"])
        return True

    @classmethod
    async def refuse_bottle(cls, bottle_id: int) -> bool:
        """
        拒绝漂流瓶

        参数:
            bottle_id: 漂流瓶ID

        返回:
            bool: 操作成功返回True
        """
        record = await cls.get_by_id(bottle_id)
        if not record:
            return False
        record.status = 100
        await record.save(update_fields=["status", "update_time"])
        return True

    @classmethod
    async def get_pending_count(cls) -> int:
        """
        获取待审核漂流瓶数量

        返回:
            int: 待审核数量
        """
        return await cls.filter(status=0).count()

    @classmethod
    async def get_random_pending(cls) -> "BottleRecord | None":
        """
        随机获取一个待审核的漂流瓶

        返回:
            BottleRecord | None: 随机待审核记录，不存在返回None
        """
        import random

        records = await cls.filter(status=0).all()
        if not records:
            return None
        return random.choice(records)

    @classmethod
    async def add_like(cls, bottle_id: int) -> int | None:
        """
        为漂流瓶点赞

        参数:
            bottle_id: 漂流瓶ID

        返回:
            int | None: 更新后的点赞数，不存在返回None
        """
        record = await cls.get_by_id(bottle_id)
        if not record:
            return None
        record.like_count += 1
        await record.save(update_fields=["like_count", "update_time"])
        return record.like_count


class BottleImage(Model):
    """漂流瓶图片记录模型"""

    __tablename__ = "bottle_image"
    __table_args__: ClassVar[dict] = {
        "comment": "漂流瓶图片记录表，存储图片元数据与床图路径"
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增ID"
    )
    bottle_id: Mapped[int] = mapped_column(
        Integer, index=True, comment="关联的漂流瓶ID"
    )
    filename: Mapped[str] = mapped_column(
        String(500), comment="床图存储文件名"
    )
    image_index: Mapped[int] = mapped_column(
        Integer, default=0, comment="图片序号"
    )
    width: Mapped[int] = mapped_column(
        Integer, default=0, comment="图片宽度"
    )
    height: Mapped[int] = mapped_column(
        Integer, default=0, comment="图片高度"
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, index=True, comment="是否已删除"
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间"
    )

    @classmethod
    async def get_next_index(cls, bottle_id: int) -> int:
        """
        获取指定漂流瓶的下一个图片序号

        参数:
            bottle_id: 漂流瓶ID

        返回:
            int: 下一个可用序号
        """
        result = await cls.filter(
            bottle_id=bottle_id, is_deleted=False
        ).max(cls.image_index)
        return (result or -1) + 1

    @classmethod
    async def create_image(
        cls,
        bottle_id: int,
        filename: str,
        image_index: int,
        width: int = 0,
        height: int = 0,
    ) -> "BottleImage":
        """
        创建图片记录

        参数:
            bottle_id: 漂流瓶ID
            filename: 床图存储文件名
            image_index: 图片序号
            width: 图片宽度
            height: 图片高度

        返回:
            BottleImage: 创建的记录
        """
        return await cls.create(
            bottle_id=bottle_id,
            filename=filename,
            image_index=image_index,
            width=width,
            height=height,
        )

    @classmethod
    async def get_images_by_bottle_id(
        cls, bottle_id: int
    ) -> list["BottleImage"]:
        """
        获取漂流瓶的所有图片记录

        参数:
            bottle_id: 漂流瓶ID

        返回:
            list[BottleImage]: 图片记录列表
        """
        return await cls.filter(
            bottle_id=bottle_id, is_deleted=False
        ).order_by("image_index").all()

    @classmethod
    async def soft_delete_by_bottle_id(cls, bottle_id: int) -> int:
        """
        软删除指定漂流瓶的所有图片记录

        参数:
            bottle_id: 漂流瓶ID

        返回:
            int: 删除的记录数量
        """
        images = await cls.filter(
            bottle_id=bottle_id, is_deleted=False
        ).all()
        count = 0
        for image in images:
            image.is_deleted = True
            await image.save(update_fields=["is_deleted"])
            count += 1
        return count


class BottleComment(Model):
    """漂流瓶评论模型"""

    __tablename__ = "bottle_comment"
    __table_args__: ClassVar[dict] = {
        "comment": "漂流瓶评论表，存储评论内容与审核状态"
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="评论ID"
    )
    bottle_id: Mapped[int] = mapped_column(
        Integer, index=True, comment="关联的漂流瓶ID"
    )
    content: Mapped[str] = mapped_column(Text, comment="评论内容")
    user_id: Mapped[str] = mapped_column(
        String(255), comment="评论者用户ID"
    )
    status: Mapped[int] = mapped_column(
        Integer, default=0, index=True, comment="状态: 0待审核, 100已拒绝, 200已通过"
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间"
    )

    @classmethod
    async def add_comment(
        cls, bottle_id: int, content: str, user_id: str
    ) -> "BottleComment":
        """
        添加评论

        参数:
            bottle_id: 漂流瓶ID
            content: 评论内容
            user_id: 评论者用户ID

        返回:
            BottleComment: 创建的评论记录
        """
        return await cls.create(
            bottle_id=bottle_id,
            content=content,
            user_id=user_id,
            status=0,
        )

    @classmethod
    async def get_approved_comments(
        cls, bottle_id: int
    ) -> list["BottleComment"]:
        """
        获取漂流瓶的已通过评论

        参数:
            bottle_id: 漂流瓶ID

        返回:
            list[BottleComment]: 评论列表
        """
        return await cls.filter(
            bottle_id=bottle_id, status=200
        ).order_by("create_time").all()

    @classmethod
    async def approve_comment(cls, comment_id: int) -> bool:
        """
        审核通过评论

        参数:
            comment_id: 评论ID

        返回:
            bool: 操作成功返回True
        """
        comment = await cls.safe_get_or_none(id=comment_id)
        if not comment:
            return False
        comment.status = 200
        await comment.save(update_fields=["status"])
        return True

    @classmethod
    async def refuse_comment(cls, comment_id: int) -> bool:
        """
        拒绝评论

        参数:
            comment_id: 评论ID

        返回:
            bool: 操作成功返回True
        """
        comment = await cls.safe_get_or_none(id=comment_id)
        if not comment:
            return False
        comment.status = 100
        await comment.save(update_fields=["status"])
        return True

    @classmethod
    async def get_random_pending(cls) -> "BottleComment | None":
        """
        随机获取一个待审核评论

        返回:
            BottleComment | None: 随机待审核评论，不存在返回None
        """
        import random

        comments = await cls.filter(status=0).all()
        if not comments:
            return None
        return random.choice(comments)


class BottleLike(Model):
    """漂流瓶点赞记录模型"""

    __tablename__ = "bottle_like"
    __table_args__: ClassVar[dict] = {
        "comment": "漂流瓶点赞记录表，防止重复点赞"
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增ID"
    )
    bottle_id: Mapped[int] = mapped_column(
        Integer, index=True, comment="漂流瓶ID"
    )
    user_id: Mapped[str] = mapped_column(
        String(255), index=True, comment="点赞用户ID"
    )

    @classmethod
    async def has_liked(cls, bottle_id: int, user_id: str) -> bool:
        """
        检查用户是否已点赞

        参数:
            bottle_id: 漂流瓶ID
            user_id: 用户ID

        返回:
            bool: 已点赞返回True
        """
        return await cls.filter(
            bottle_id=bottle_id, user_id=user_id
        ).exists()

    @classmethod
    async def add_like(cls, bottle_id: int, user_id: str) -> "BottleLike":
        """
        添加点赞记录

        参数:
            bottle_id: 漂流瓶ID
            user_id: 用户ID

        返回:
            BottleLike: 创建的记录
        """
        return await cls.create(bottle_id=bottle_id, user_id=user_id)
