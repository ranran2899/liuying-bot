"""视觉能力管理路由

提供AI插件视觉provider能力查询与首选provider设置接口。
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from liuying.liuying_plugins.AI.core.vision import vision_router

from ..deps import require_superuser

__all__ = ["build_vision_router"]


def build_vision_router() -> APIRouter:
    """构建视觉能力路由

    Returns:
        APIRouter: 视觉能力路由器
    """
    router = APIRouter(prefix="/vision", tags=["AI-视觉能力"])

    @router.get("/capability")
    async def vision_capability() -> dict[str, Any]:
        """获取视觉能力路由摘要

        返回:
            dict: 各provider能力概览
        """
        try:
            summary = vision_router.get_capability_summary()
            summary["timestamp"] = datetime.now().isoformat()
            return summary
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.post("/preferred")
    async def set_vision_preferred(
        provider: str,
        model: str,
        _: None = Depends(require_superuser),
    ) -> dict[str, Any]:
        """设置首选视觉provider

        参数:
            provider: provider名
            model: 模型名

        返回:
            dict: 操作结果
        """
        try:
            vision_router.set_preferred(provider, model)
            return {
                "ok": True,
                "provider": provider,
                "model": model,
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    return router
