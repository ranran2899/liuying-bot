"""Token统计路由

提供AI插件Token使用统计查询接口。
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from liuying.liuying_plugins.AI.core.llm import token_ledger

__all__ = ["build_token_router"]


def build_token_router() -> APIRouter:
    """构建Token统计路由

    Returns:
        APIRouter: Token统计路由器
    """
    router = APIRouter(prefix="/token", tags=["AI-Token统计"])

    @router.get("/summary")
    async def token_summary(days: int = 7) -> dict[str, Any]:
        """获取Token使用统计

        参数:
            days: 统计天数

        返回:
            dict: Token统计
        """
        try:
            hours = min(max(days, 1), 90) * 24
            stats = await token_ledger.get_summary(hours=hours)
            return {
                "days": days,
                "stats": stats,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    return router
