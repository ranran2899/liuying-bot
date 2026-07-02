"""健康检查与功能体检路由

提供WebUI自身健康检查与AI插件功能体检接口。
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from liuying.liuying_plugins.AI.core.runtime import runtime_switch

from ..deps import require_superuser

__all__ = ["build_health_router"]


def build_health_router() -> APIRouter:
    """构建健康检查路由

    Returns:
        APIRouter: 健康检查路由器
    """
    router = APIRouter(prefix="/health", tags=["AI-健康检查"])

    @router.get("")
    async def health() -> dict[str, str]:
        """WebUI自身健康检查"""
        return {"status": "ok"}

    @router.get("/full")
    async def health_full(
        user_id: str = "",
        _: None = Depends(require_superuser),
    ) -> dict[str, Any]:
        """AI功能体检：返回所有功能开关状态与计数

        参数:
            user_id: 请求方用户ID（鉴权用）

        返回:
            dict: 功能体检结果
        """
        try:
            return runtime_switch.health_check()
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.get("/timestamp")
    async def server_time() -> dict[str, str]:
        """获取服务器当前时间"""
        return {"timestamp": datetime.now().isoformat()}

    return router
