"""记忆系统查看路由

提供AI插件记忆摘要查询与清理接口。
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from liuying.liuying_plugins.AI.core.memory import memory_manager

from ..deps import require_superuser

__all__ = ["build_memory_router"]


def build_memory_router() -> APIRouter:
    """构建记忆管理路由

    Returns:
        APIRouter: 记忆管理路由器
    """
    router = APIRouter(prefix="/memory", tags=["AI-记忆管理"])

    @router.get("/summary")
    async def memory_summary(
        user_id: str = "",
        group_id: str = "",
        limit: int = 10,
    ) -> dict[str, Any]:
        """获取记忆摘要

        参数:
            user_id: 用户ID（空时查全局）
            group_id: 群组ID（可选）
            limit: 返回条数上限

        返回:
            dict: 记忆条目列表
        """
        try:
            memories = await memory_manager.get_memory_summary(
                user_id or "global",
                group_id or None,
                limit=min(max(limit, 1), 50),
            )
            return {
                "count": len(memories),
                "memories": memories,
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.post("/clear")
    async def clear_user_memory(
        user_id: str,
        group_id: str = "",
        persona_name: str = "default",
        _: None = Depends(require_superuser),
    ) -> dict[str, Any]:
        """清空指定用户的记忆

        参数:
            user_id: 用户ID
            group_id: 群组ID（可选）
            persona_name: 人格名（默认default）

        返回:
            dict: 操作结果
        """
        try:
            await memory_manager.clear_user_memory(
                user_id,
                persona_name=persona_name,
                group_id=group_id or None,
            )
            return {
                "ok": True,
                "user_id": user_id,
                "persona_name": persona_name,
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    return router
