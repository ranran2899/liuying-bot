"""权限检查路由

提供AI插件权限等级查询接口。
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from liuying.liuying_plugins.AI.core.safety import check_permission

__all__ = ["build_acl_router"]


def build_acl_router() -> APIRouter:
    """构建权限检查路由

    Returns:
        APIRouter: 权限检查路由器
    """
    router = APIRouter(prefix="/acl", tags=["AI-权限检查"])

    @router.get("/check")
    async def acl_check(
        user_id: str,
        level: int = 5,
        group_id: str = "",
    ) -> dict[str, Any]:
        """检查用户权限

        参数:
            user_id: 用户ID
            level: 需要的等级
            group_id: 群组ID

        返回:
            dict: 权限检查结果
        """
        try:
            result = await check_permission(
                user_id,
                level,
                group_id=group_id or None,
            )
            return {
                "user_id": user_id,
                "required_level": level,
                "allowed": result.allowed,
                "reason": result.reason,
                "user_level": result.user_level,
                "is_superuser": result.is_superuser,
                "is_blacklisted": result.is_blacklisted,
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    return router
