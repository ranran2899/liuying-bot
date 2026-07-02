"""情绪状态查看路由

提供AI插件情绪状态查询接口。
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from liuying.liuying_plugins.AI.core.emotion import emotion_manager

__all__ = ["build_emotion_router"]


def build_emotion_router() -> APIRouter:
    """构建情绪状态路由

    Returns:
        APIRouter: 情绪状态路由器
    """
    router = APIRouter(prefix="/emotion", tags=["AI-情绪状态"])

    @router.get("/{user_id}")
    async def emotion_state(user_id: str) -> dict[str, Any]:
        """获取用户情绪状态

        参数:
            user_id: 用户ID

        返回:
            dict: 情绪状态信息
        """
        try:
            state = await emotion_manager.get_state(user_id)
            return {
                "user_id": user_id,
                "mood": state.mood,
                "energy": state.energy,
                "relation_warmth": state.relation_warmth,
                "pending_thoughts": state.pending_thoughts,
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    return router
