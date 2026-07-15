"""AI 视觉/知识库/Token/权限路由

提供AI插件视觉能力查询、知识库统计、Token使用统计与权限检查接口。
"""

from dataclasses import asdict
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from liuying.liuying_plugins.AI.core.knowledge import knowledge_store
from liuying.liuying_plugins.AI.core.llm import token_ledger
from liuying.liuying_plugins.AI.core.safety import AclChecker
from liuying.liuying_plugins.AI.core.vision import vision_router

from ....base_model import Result
from ....utils import authentication
from .model import VisionPreferredRequest

router = APIRouter(prefix="/ai", dependencies=[authentication()])


@router.get(
    "/vision/capability",
    response_model=Result[dict[str, Any]],
    response_class=JSONResponse,
    description="获取视觉能力",
)
async def _() -> Result[dict[str, Any]]:
    """获取视觉能力路由摘要"""
    summary = vision_router.get_capability_summary()
    summary["timestamp"] = datetime.now().isoformat()
    return Result.ok(summary)


@router.post(
    "/vision/preferred",
    response_model=Result[dict[str, Any]],
    response_class=JSONResponse,
    description="设置首选视觉provider",
)
async def _(body: VisionPreferredRequest) -> Result[dict[str, Any]]:
    """设置首选视觉provider"""
    vision_router.set_preferred(body.provider, body.model)
    return Result.ok(
        {"ok": True, "provider": body.provider, "model": body.model},
        "首选视觉provider已设置",
    )


@router.get(
    "/knowledge/stats",
    response_model=Result[dict[str, Any]],
    response_class=JSONResponse,
    description="获取知识库统计",
)
async def _() -> Result[dict[str, Any]]:
    """获取插件知识库统计

    KnowledgeStats 为 dataclass，通过 asdict 序列化为字典。
    """
    stats = await knowledge_store.get_stats()
    stats_dict = asdict(stats)
    stats_dict["last_scan"] = (
        stats_dict["last_scan"].isoformat()
        if stats_dict.get("last_scan")
        else None
    )
    return Result.ok(
        {"stats": stats_dict, "timestamp": datetime.now().isoformat()}
    )


@router.get(
    "/token/summary",
    response_model=Result[dict[str, Any]],
    response_class=JSONResponse,
    description="获取Token统计",
)
async def _(days: int = 7) -> Result[dict[str, Any]]:
    """获取Token使用统计

    参数:
        days: 统计天数
    """
    hours = min(max(days, 1), 90) * 24
    stats = await token_ledger.get_summary(hours=hours)
    return Result.ok(
        {
            "days": days,
            "stats": stats,
            "timestamp": datetime.now().isoformat(),
        }
    )


@router.get(
    "/acl/check",
    response_model=Result[dict[str, Any]],
    response_class=JSONResponse,
    description="检查用户权限",
)
async def _(
    user_id: str,
    level: int = 5,
    group_id: str = "",
) -> Result[dict[str, Any]]:
    """检查用户权限

    参数:
        user_id: 用户ID
        level: 需要的等级
        group_id: 群组ID
    """
    result = await AclChecker.check_permission(
        user_id,
        level,
        group_id=group_id or None,
    )
    return Result.ok(
        {
            "user_id": user_id,
            "required_level": level,
            "allowed": result.allowed,
            "reason": result.reason,
            "user_level": result.user_level,
            "is_superuser": result.is_superuser,
            "is_blacklisted": result.is_blacklisted,
        }
    )

