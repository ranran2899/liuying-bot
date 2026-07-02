"""知识库统计路由

提供AI插件知识库统计查询接口。
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from liuying.liuying_plugins.AI.core.knowledge import knowledge_store

__all__ = ["build_knowledge_router"]


def build_knowledge_router() -> APIRouter:
    """构建知识库路由

    Returns:
        APIRouter: 知识库路由器
    """
    router = APIRouter(prefix="/knowledge", tags=["AI-知识库"])

    @router.get("/stats")
    async def knowledge_stats() -> dict[str, Any]:
        """获取插件知识库统计

        返回:
            dict: 知识库统计信息
        """
        try:
            stats = await knowledge_store.get_stats()
            return {
                "stats": stats,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    return router
