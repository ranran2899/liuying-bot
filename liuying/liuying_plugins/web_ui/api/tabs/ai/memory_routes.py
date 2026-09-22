"""AI 记忆/情绪/群上下文路由

提供AI插件记忆摘要查询与清理、用户情绪状态查询、群上下文列表查询。
"""

import json
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from liuying.liuying_plugins.AI.core.emotion import emotion_manager
from liuying.liuying_plugins.AI.core.memory import memory_manager
from liuying.liuying_plugins.AI.models.group_context import GroupContextSnapshot

from ....base_model import Result
from ....utils import authentication
from .model import MemoryClearRequest

router = APIRouter(prefix="/ai", dependencies=[authentication()])


@router.get(
    "/memory/summary",
    response_model=Result[dict[str, Any]],
    response_class=JSONResponse,
    description="获取记忆摘要",
)
async def _(
    user_id: str = "",
    group_id: str = "",
    limit: int = 10,
) -> Result[dict[str, Any]]:
    """获取记忆摘要

    参数:
        user_id: 用户ID（空时查全局）
        group_id: 群组ID（可选）
        limit: 返回条数上限
    """
    memories = await memory_manager.get_memory_summary(
        user_id or "global",
        group_id or None,
        limit=min(max(limit, 1), 50),
    )
    return Result.ok(
        {"count": len(memories), "memories": memories}
    )


@router.post(
    "/memory/clear",
    response_model=Result[dict[str, Any]],
    response_class=JSONResponse,
    description="清空用户记忆",
)
async def _(body: MemoryClearRequest) -> Result[dict[str, Any]]:
    """清空指定用户的记忆"""
    await memory_manager.clear_user_memory(
        body.user_id,
        persona_name=body.persona_name,
        group_id=body.group_id or None,
    )
    return Result.ok(
        {
            "ok": True,
            "user_id": body.user_id,
            "persona_name": body.persona_name,
        },
        "记忆已清空",
    )


@router.get(
    "/emotion/{user_id}",
    response_model=Result[dict[str, Any]],
    response_class=JSONResponse,
    description="获取用户情绪状态",
)
async def _(user_id: str) -> Result[dict[str, Any]]:
    """获取用户情绪状态

    pending_thoughts 在数据库中存储为JSON字符串，此处解析为列表返回。
    """
    state = await emotion_manager.get_state(user_id)
    try:
        thoughts = json.loads(state.pending_thoughts or "[]")
    except (json.JSONDecodeError, TypeError):
        thoughts = []
    return Result.ok(
        {
            "user_id": user_id,
            "mood": state.mood,
            "energy": state.energy,
            "relation_warmth": state.relation_warmth,
            "pending_thoughts": thoughts,
        }
    )


@router.get(
    "/groups",
    response_model=Result[list[dict[str, Any]]],
    response_class=JSONResponse,
    description="列出活跃群上下文",
)
async def _() -> Result[list[dict[str, Any]]]:
    """列出活跃群上下文"""
    groups = await GroupContextSnapshot.filter(is_active=True).all()
    return Result.ok(
        [
            {
                "group_id": str(g.group_id),
                "style": g.style or "",
                "summary": g.summary or "",
                "last_activity": (
                    g.last_activity_time.isoformat()
                    if g.last_activity_time
                    else ""
                ),
            }
            for g in groups
        ]
    )
