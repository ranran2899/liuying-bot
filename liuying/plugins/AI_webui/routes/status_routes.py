"""插件状态查询路由

提供AI插件整体运行状态概览。
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter
from liuying.liuying_plugins.AI.config import get_config as get_ai_config

__all__ = ["build_status_router"]


def build_status_router() -> APIRouter:
    """构建状态查询路由

    Returns:
        APIRouter: 状态查询路由器
    """
    router = APIRouter(prefix="/status", tags=["AI-状态查询"])

    @router.get("")
    async def status() -> dict[str, Any]:
        """获取AI插件运行状态

        返回:
            dict: 包含各功能模块开关与当前人格
        """
        return {
            "enabled": get_ai_config("ENABLE_AI", True),
            "persona": get_ai_config("DEFAULT_PERSONA", "liuying"),
            "agent_enabled": get_ai_config("AGENT_ENABLED", True),
            "memory_enabled": get_ai_config("MEMORY_ENABLED", True),
            "tts_enabled": get_ai_config("TTS_ENABLED", False),
            "safety_filter_enabled": get_ai_config(
                "SAFETY_FILTER_ENABLED", True
            ),
            "fragment_style": get_ai_config("FRAGMENT_STYLE", "prompt"),
            "vision_enabled": get_ai_config("VISION_ENABLED", True),
            "timestamp": datetime.now().isoformat(),
        }

    return router
