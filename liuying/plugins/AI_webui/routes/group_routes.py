"""群上下文查看路由

提供AI插件群上下文列表查询接口。
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from liuying.liuying_plugins.AI.models.group_context import GroupContextSnapshot

__all__ = ["build_group_router"]


def build_group_router() -> APIRouter:
    """构建群上下文路由

    Returns:
        APIRouter: 群上下文路由器
    """
    router = APIRouter(prefix="/groups", tags=["AI-群上下文"])

    @router.get("")
    async def list_groups() -> list[dict[str, Any]]:
        """列出活跃群上下文

        返回:
            list: 群上下文列表
        """
        try:
            groups = await GroupContextSnapshot.filter(
                is_active=True
            ).all()
            return [
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
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    return router
