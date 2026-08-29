"""漂流瓶管理 WebUI 数据源"""
import base64

from liuying.models._user.user_info import UserInfo
from liuying.models.bottle import (
    BottleComment,
    BottleImage,
    BottleLike,
    BottleRecord,
)
from liuying.utils.bed_layout import BedLayout
from liuying.utils.enum import StorageType
from liuying.utils.log import logger

from .model import (
    BottleBatchDeleteResult,
    BottleImagesResult,
    BottleListItem,
    BottleReviewItem,
    BottleReviewStats,
    CommentReviewItem,
)


class BottleReviewDataSource:
    """漂流瓶审核数据源，封装所有业务逻辑"""

    @staticmethod
    async def get_stats() -> BottleReviewStats:
        """获取审核统计信息

        返回:
            BottleReviewStats: 统计数据
        """
        pending_bottles = await BottleRecord.get_pending_count()
        pending_comments = await BottleComment.filter(status=0).count()
        total_bottles = await BottleRecord.filter().count()
        total_comments = await BottleComment.filter().count()
        return BottleReviewStats(
            pending_bottles=pending_bottles,
            pending_comments=pending_comments,
            total_bottles=total_bottles,
            total_comments=total_comments,
        )

    @staticmethod
    async def _resolve_uid(user_id: str) -> str:
        """解析用户UID，失败返回空字符串

        参数:
            user_id: 用户ID

        返回:
            str: 用户UID
        """
        try:
            return await UserInfo.get_user_uid(user_id) or ""
        except Exception as e:
            logger.warning(
                f"获取用户UID失败 user_id={user_id}: {e}",
                "BottleWeb",
            )
            return ""

    @staticmethod
    async def _load_images_base64(bottle_id: int) -> list[str]:
        """加载漂流瓶图片并转 base64

        参数:
            bottle_id: 漂流瓶ID

        返回:
            list[str]: base64 编码图片列表
        """
        images = await BottleImage.get_images_by_bottle_id(bottle_id)
        result: list[str] = []
        for img in images:
            data = await BedLayout.get_bytes(
                img.filename, storage_type=StorageType.LOCAL
            )
            if data:
                result.append(base64.b64encode(data).decode("utf-8"))
        return result

    @classmethod
    async def get_bottle_images(
        cls, bottle_id: int
    ) -> BottleImagesResult | None:
        """获取漂流瓶图片列表

        参数:
            bottle_id: 漂流瓶ID

        返回:
            BottleImagesResult | None: 图片结果，瓶子不存在返回None
        """
        record = await BottleRecord.get_by_id(bottle_id)
        if not record:
            return None
        images = await cls._load_images_base64(bottle_id)
        return BottleImagesResult(bottle_id=bottle_id, images=images)

    @classmethod
    async def get_random_pending_bottle(cls) -> BottleReviewItem | None:
        """随机获取一个待审核漂流瓶

        返回:
            BottleReviewItem | None: 漂流瓶数据，无数据返回None
        """
        bottle = await BottleRecord.get_random_pending()
        if not bottle:
            return None
        uid = await cls._resolve_uid(bottle.user_id)
        images = await cls._load_images_base64(bottle.id)
        return BottleReviewItem(
            id=bottle.id,
            content=bottle.content or "",
            user_id=bottle.user_id,
            uid=uid,
            platform=bottle.platform,
            status=bottle.status,
            like_count=bottle.like_count,
            create_time=bottle.create_time,
            images=images,
        )

    @classmethod
    async def get_random_pending_comment(cls) -> CommentReviewItem | None:
        """随机获取一个待审核评论

        返回:
            CommentReviewItem | None: 评论数据，无数据返回None
        """
        comment = await BottleComment.get_random_pending()
        if not comment:
            return None
        uid = await cls._resolve_uid(comment.user_id)
        return CommentReviewItem(
            id=comment.id,
            bottle_id=comment.bottle_id,
            content=comment.content,
            user_id=comment.user_id,
            uid=uid,
            status=comment.status,
            create_time=comment.create_time,
        )

    @staticmethod
    async def approve_bottle(bottle_id: int) -> bool:
        """审核通过漂流瓶

        参数:
            bottle_id: 漂流瓶ID

        返回:
            bool: 操作是否成功
        """
        return await BottleRecord.approve_bottle(bottle_id)

    @staticmethod
    async def refuse_bottle(bottle_id: int) -> bool:
        """拒绝漂流瓶并软删除关联图片

        参数:
            bottle_id: 漂流瓶ID

        返回:
            bool: 操作是否成功
        """
        success = await BottleRecord.refuse_bottle(bottle_id)
        if success:
            await BottleImage.soft_delete_by_bottle_id(bottle_id)
        return success

    @staticmethod
    async def approve_comment(comment_id: int) -> bool:
        """审核通过评论

        参数:
            comment_id: 评论ID

        返回:
            bool: 操作是否成功
        """
        return await BottleComment.approve_comment(comment_id)

    @staticmethod
    async def refuse_comment(comment_id: int) -> bool:
        """拒绝评论

        参数:
            comment_id: 评论ID

        返回:
            bool: 操作是否成功
        """
        return await BottleComment.refuse_comment(comment_id)

    @staticmethod
    async def get_bottle_list(
        index: int, size: int, status: int | None = None
    ) -> tuple[int, list[BottleListItem]]:
        """分页获取漂流瓶列表

        参数:
            index: 页码（从1开始）
            size: 每页数量
            status: 状态筛选，None表示全部

        返回:
            tuple[int, list[BottleListItem]]: (总数, 列表项)
        """
        query = BottleRecord.filter()
        if status is not None:
            query = query.filter(status=status)
        total = await query.count()
        records = (
            await query.order_by("-id")
            .offset((index - 1) * size)
            .limit(size)
            .all()
        )
        items: list[BottleListItem] = []
        for record in records:
            image_count = await BottleImage.filter(
                bottle_id=record.id, is_deleted=False
            ).count()
            items.append(
                BottleListItem(
                    id=record.id,
                    content=record.content or "",
                    user_id=record.user_id,
                    platform=record.platform,
                    status=record.status,
                    like_count=record.like_count,
                    create_time=record.create_time,
                    image_count=image_count,
                )
            )
        return total, items

    @staticmethod
    async def _cleanup_bottle_relations(bottle_id: int) -> None:
        """清理漂流瓶关联数据（图片软删除、评论与点赞硬删除）

        参数:
            bottle_id: 漂流瓶ID
        """
        await BottleImage.soft_delete_by_bottle_id(bottle_id)
        await BottleComment.filter(bottle_id=bottle_id).delete()
        await BottleLike.filter(bottle_id=bottle_id).delete()

    @classmethod
    async def delete_bottle(cls, bottle_id: int) -> bool:
        """删除漂流瓶及其关联数据

        参数:
            bottle_id: 漂流瓶ID

        返回:
            bool: 操作是否成功
        """
        record = await BottleRecord.get_by_id(bottle_id)
        if not record:
            return False
        await cls._cleanup_bottle_relations(bottle_id)
        await record.delete()
        return True

    @classmethod
    async def batch_delete_bottles(
        cls, ids: list[int]
    ) -> BottleBatchDeleteResult:
        """批量删除漂流瓶

        参数:
            ids: 漂流瓶ID列表

        返回:
            BottleBatchDeleteResult: 删除结果
        """
        success: list[int] = []
        failed: list[int] = []
        for bottle_id in ids:
            try:
                ok = await cls.delete_bottle(bottle_id)
                if ok:
                    success.append(bottle_id)
                else:
                    failed.append(bottle_id)
            except Exception as e:
                logger.warning(
                    f"批量删除漂流瓶失败 id={bottle_id}: {e}",
                    "BottleWeb",
                )
                failed.append(bottle_id)
        return BottleBatchDeleteResult(
            success=success,
            failed=failed,
            total=len(ids),
        )
