"""健康检查与服务器时间路由

提供本体 WebUI 自身健康检查与服务器时间接口。
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter

__all__ = ["build_health_router"]


def build_health_router() -> APIRouter:
    """构建健康检查路由

    Returns:
        APIRouter: 健康检查路由器
    """
    router = APIRouter(prefix="/health", tags=["WebUI-健康检查"])

    @router.get("")
    async def health() -> dict[str, str]:
        """本体 WebUI 自身健康检查"""
        return {"status": "ok"}

    @router.get("/timestamp")
    async def server_time() -> dict[str, str]:
        """获取服务器当前时间"""
        return {"timestamp": datetime.now().isoformat()}

    @router.get("/full")
    async def health_full() -> dict[str, Any]:
        """本体服务体检：返回各核心子系统可用性"""
        from nonebot import get_bots
        from liuying.utils.apscheduler.manager import task_manager

        bots = get_bots()
        tasks = task_manager.get_all_tasks()
        return {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "connected_bots": len(bots),
            "scheduler_started": task_manager._started,
            "task_count": len(tasks),
        }

    return router
