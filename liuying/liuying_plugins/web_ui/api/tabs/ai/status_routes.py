"""AI 状态与健康检查路由

提供AI插件整体运行状态概览、健康检查与服务器时间。
"""

from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from liuying.liuying_plugins.AI.config import (
    get_config as get_ai_config,
)
from liuying.liuying_plugins.AI.core.runtime import runtime_switch

from ....base_model import Result
from ....utils import authentication

router = APIRouter(prefix="/ai", dependencies=[authentication()])


@router.get(
    "/status",
    response_model=Result[dict],
    response_class=JSONResponse,
    description="获取AI插件运行状态",
)
async def _() -> Result[dict]:
    """获取AI插件运行状态

    返回:
        Result[dict]: 包含各功能模块开关与当前人格
    """
    return Result.ok(
        {
            "enabled": get_ai_config("ENABLE_AI", False),
            "persona": get_ai_config("DEFAULT_PERSONA", "liuying"),
            "agent_enabled": get_ai_config("AGENT", {}).get(
                "enabled", True
            ),
            "memory_enabled": get_ai_config("MEMORY_ENABLED", True),
            "tts_enabled": get_ai_config("TTS", {}).get("enabled", False),
            "safety_filter_enabled": get_ai_config(
                "SAFETY_FILTER_ENABLED", True
            ),
            "fragment_style": get_ai_config("FRAGMENT", {}).get(
                "style", "prompt"
            ),
            "vision_enabled": get_ai_config("VISION", {}).get(
                "enabled", True
            ),
            "timestamp": datetime.now().isoformat(),
        }
    )


@router.get(
    "/health",
    response_model=Result[dict],
    response_class=JSONResponse,
    description="AI功能体检",
)
async def health() -> Result[dict]:
    """AI功能体检：返回所有功能开关状态与计数"""
    return Result.ok(runtime_switch.health_check())


@router.get(
    "/timestamp",
    response_model=Result[dict],
    response_class=JSONResponse,
    description="获取服务器时间",
)
async def server_time() -> Result[dict[str, str]]:
    """获取服务器当前时间"""
    return Result.ok({"timestamp": datetime.now().isoformat()})
