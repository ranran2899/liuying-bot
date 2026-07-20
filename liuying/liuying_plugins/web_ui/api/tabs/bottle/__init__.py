"""漂流瓶管理 WebUI 路由"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from liuying.utils.log import logger

from ....base_model import Result
from ....utils import authentication
from .data_source import BottleReviewDataSource
from .model import (
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
