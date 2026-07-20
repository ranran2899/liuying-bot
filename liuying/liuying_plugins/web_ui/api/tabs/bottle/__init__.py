"""漂流瓶管理 WebUI 路由"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from liuying.utils.log import logger

from ....base_model import BaseResultModel, Result
from ....utils import authentication
from .data_source import BottleReviewDataSource
from .model import (
    BottleBatchDeletePayload,
    BottleBatchDeleteResult,
    BottleImagesResult,
    BottleOperationResult,
    BottleReviewItem,
    BottleReviewStats,
    CommentReviewItem,
)

router = APIRouter(prefix="/bottle")


@router.get(
    "/get_stats",
    dependencies=[authentication()],
    response_model=Result[BottleReviewStats],
    response_class=JSONResponse,
    description="获取漂流瓶审核统计",
)
async def _() -> Result[BottleReviewStats]:
    """获取漂流瓶审核统计信息"""
    try:
        return Result.ok(
            await BottleReviewDataSource.get_stats(), "拿到信息啦!"
        )
    except Exception as e:
        logger.error(f"{router.prefix}/get_stats 调用错误", command="WebUi", e=e)
        return Result.fail(f"发生了一点错误捏 {type(e)}: {e}")


@router.get(
    "/bottles/random",
    dependencies=[authentication()],
    response_model=Result[BottleReviewItem],
    response_class=JSONResponse,
    description="随机获取待审核漂流瓶",
)
async def _() -> Result[BottleReviewItem]:
    """随机获取一个待审核漂流瓶"""
    try:
        item = await BottleReviewDataSource.get_random_pending_bottle()
        if not item:
            return Result.warning_("没有待审核的瓶子")
        return Result.ok(item, "拿到信息啦!")
    except Exception as e:
        logger.error(
            f"{router.prefix}/bottles/random 调用错误", command="WebUi", e=e
        )
        return Result.fail(f"发生了一点错误捏 {type(e)}: {e}")


@router.post(
    "/bottles/approve/{bottle_id}",
    dependencies=[authentication()],
    response_model=Result[BottleOperationResult],
    response_class=JSONResponse,
    description="审核通过漂流瓶",
)
async def _(bottle_id: int) -> Result[BottleOperationResult]:
    """审核通过指定漂流瓶"""
    try:
        success = await BottleReviewDataSource.approve_bottle(bottle_id)
        if not success:
            return Result.fail("漂流瓶不存在")
        return Result.ok(
            BottleOperationResult(id=bottle_id, status="approved"),
            "审核通过成功!",
        )
    except Exception as e:
        logger.error(
            f"{router.prefix}/bottles/approve 调用错误",
            command="WebUi",
            e=e,
        )
        return Result.fail(f"发生了一点错误捏 {type(e)}: {e}")


@router.post(
    "/bottles/refuse/{bottle_id}",
    dependencies=[authentication()],
    response_model=Result[BottleOperationResult],
    response_class=JSONResponse,
    description="拒绝漂流瓶",
)
async def _(bottle_id: int) -> Result[BottleOperationResult]:
    """拒绝指定漂流瓶并软删除关联图片"""
    try:
        success = await BottleReviewDataSource.refuse_bottle(bottle_id)
        if not success:
            return Result.fail("漂流瓶不存在")
        return Result.ok(
            BottleOperationResult(id=bottle_id, status="refused"),
            "已拒绝该瓶子!",
        )
    except Exception as e:
        logger.error(
            f"{router.prefix}/bottles/refuse 调用错误",
            command="WebUi",
            e=e,
        )
        return Result.fail(f"发生了一点错误捏 {type(e)}: {e}")


@router.get(
    "/comments/random",
    dependencies=[authentication()],
    response_model=Result[CommentReviewItem],
    response_class=JSONResponse,
    description="随机获取待审核评论",
)
async def _() -> Result[CommentReviewItem]:
    """随机获取一个待审核评论"""
    try:
        item = await BottleReviewDataSource.get_random_pending_comment()
        if not item:
            return Result.warning_("没有待审核的评论")
        return Result.ok(item, "拿到信息啦!")
    except Exception as e:
        logger.error(
            f"{router.prefix}/comments/random 调用错误",
            command="WebUi",
            e=e,
        )
        return Result.fail(f"发生了一点错误捏 {type(e)}: {e}")


@router.post(
    "/comments/approve/{comment_id}",
    dependencies=[authentication()],
    response_model=Result[BottleOperationResult],
    response_class=JSONResponse,
    description="审核通过评论",
)
async def _(comment_id: int) -> Result[BottleOperationResult]:
    """审核通过指定评论"""
    try:
        success = await BottleReviewDataSource.approve_comment(comment_id)
        if not success:
            return Result.fail("评论不存在")
        return Result.ok(
            BottleOperationResult(id=comment_id, status="approved"),
            "审核通过成功!",
        )
    except Exception as e:
        logger.error(
            f"{router.prefix}/comments/approve 调用错误",
            command="WebUi",
            e=e,
        )
        return Result.fail(f"发生了一点错误捏 {type(e)}: {e}")


@router.post(
    "/comments/refuse/{comment_id}",
    dependencies=[authentication()],
    response_model=Result[BottleOperationResult],
    response_class=JSONResponse,
    description="拒绝评论",
)
async def _(comment_id: int) -> Result[BottleOperationResult]:
    """拒绝指定评论"""
    try:
        success = await BottleReviewDataSource.refuse_comment(comment_id)
        if not success:
            return Result.fail("评论不存在")
        return Result.ok(
            BottleOperationResult(id=comment_id, status="refused"),
            "已拒绝该评论!",
        )
    except Exception as e:
        logger.error(
            f"{router.prefix}/comments/refuse 调用错误",
            command="WebUi",
            e=e,
        )
        return Result.fail(f"发生了一点错误捏 {type(e)}: {e}")


@router.get(
    "/bottles/list",
    dependencies=[authentication()],
    response_model=Result[BaseResultModel],
    response_class=JSONResponse,
    description="分页获取漂流瓶列表",
)
async def _(
    index: int = 1,
    size: int = 20,
    status: int | None = None,
) -> Result[BaseResultModel]:
    """分页获取漂流瓶列表，支持按状态筛选"""
    try:
        if index < 1:
            return Result.fail("页码必须大于0")
        if size < 1 or size > 100:
            return Result.fail("每页数量必须在1-100之间")
        total, items = await BottleReviewDataSource.get_bottle_list(
            index, size, status
        )
        return Result.ok(BaseResultModel(total=total, data=items))
    except Exception as e:
        logger.error(
            f"{router.prefix}/bottles/list 调用错误", command="WebUi", e=e
        )
        return Result.fail(f"发生了一点错误捏 {type(e)}: {e}")


@router.get(
    "/bottles/{bottle_id}/images",
    dependencies=[authentication()],
    response_model=Result[BottleImagesResult],
    response_class=JSONResponse,
    description="获取漂流瓶图片列表",
)
async def _(bottle_id: int) -> Result[BottleImagesResult]:
    """获取指定漂流瓶的所有图片（base64 编码）"""
    try:
        result = await BottleReviewDataSource.get_bottle_images(bottle_id)
        if not result:
            return Result.fail("漂流瓶不存在")
        return Result.ok(result, "拿到信息啦!")
    except Exception as e:
        logger.error(
            f"{router.prefix}/bottles/images 调用错误",
            command="WebUi",
            e=e,
        )
        return Result.fail(f"发生了一点错误捏 {type(e)}: {e}")


@router.delete(
    "/bottles/{bottle_id}",
    dependencies=[authentication()],
    response_model=Result[BottleOperationResult],
    response_class=JSONResponse,
    description="删除漂流瓶",
)
async def _(bottle_id: int) -> Result[BottleOperationResult]:
    """删除漂流瓶及其关联数据（图片、评论、点赞）"""
    try:
        success = await BottleReviewDataSource.delete_bottle(bottle_id)
        if not success:
            return Result.fail("漂流瓶不存在")
        return Result.ok(
            BottleOperationResult(id=bottle_id, status="deleted"),
            "删除成功!",
        )
    except Exception as e:
        logger.error(
            f"{router.prefix}/bottles/delete 调用错误",
            command="WebUi",
            e=e,
        )
        return Result.fail(f"发生了一点错误捏 {type(e)}: {e}")


@router.post(
    "/bottles/batch_delete",
    dependencies=[authentication()],
    response_model=Result[BottleBatchDeleteResult],
    response_class=JSONResponse,
    description="批量删除漂流瓶",
)
async def _(payload: BottleBatchDeletePayload) -> Result[BottleBatchDeleteResult]:
    """批量删除漂流瓶"""
    try:
        if not payload.ids:
            return Result.fail("ID列表不能为空")
        result = await BottleReviewDataSource.batch_delete_bottles(payload.ids)
        return Result.ok(result, f"成功删除 {len(result.success)} 条")
    except Exception as e:
        logger.error(
            f"{router.prefix}/bottles/batch_delete 调用错误",
            command="WebUi",
            e=e,
        )
        return Result.fail(f"发生了一点错误捏 {type(e)}: {e}")
