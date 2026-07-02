"""运行时开关管理路由

提供AI插件功能开关的状态查询与全局/群组/用户级覆盖管理。
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from liuying.liuying_plugins.AI.core.runtime import runtime_switch

from ..deps import require_superuser

__all__ = ["build_runtime_router"]


def build_runtime_router() -> APIRouter:
    """构建运行时开关路由

    Returns:
        APIRouter: 运行时开关路由器
    """
    router = APIRouter(prefix="/runtime", tags=["AI-运行时开关"])

    @router.get("")
    async def runtime_status(
        user_id: str = "",
        group_id: str = "",
    ) -> dict[str, Any]:
        """获取运行时开关状态

        参数:
            user_id: 用户ID（可选）
            group_id: 群组ID（可选）

        返回:
            dict: 各功能开关状态
        """
        try:
            statuses = runtime_switch.get_status(
                user_id=user_id or None,
                group_id=group_id or None,
            )
            return {
                "user_id": user_id or "",
                "group_id": group_id or "",
                "features": [
                    {
                        "name": s.name,
                        "enabled": s.enabled,
                        "source": s.source,
                        "config_key": s.config_key,
                    }
                    for s in statuses
                ],
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.post("/global")
    async def set_global_switch(
        feature: str,
        enabled: bool,
        _: None = Depends(require_superuser),
    ) -> dict[str, Any]:
        """设置全局开关

        参数:
            feature: 功能名
            enabled: 是否启用

        返回:
            dict: 操作结果
        """
        try:
            ok = runtime_switch.set_global(feature, enabled)
            if not ok:
                raise HTTPException(
                    status_code=400,
                    detail=f"未知功能: {feature}",
                )
            return {
                "feature": feature,
                "enabled": enabled,
                "scope": "global",
                "ok": True,
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.post("/group")
    async def set_group_switch(
        group_id: str,
        feature: str,
        enabled: bool,
        _: None = Depends(require_superuser),
    ) -> dict[str, Any]:
        """设置群组级开关覆盖

        参数:
            group_id: 群组ID
            feature: 功能名
            enabled: 是否启用

        返回:
            dict: 操作结果
        """
        try:
            ok = runtime_switch.set_group(
                group_id, feature, enabled
            )
            if not ok:
                raise HTTPException(
                    status_code=400,
                    detail=f"参数无效: {group_id}/{feature}",
                )
            return {
                "group_id": group_id,
                "feature": feature,
                "enabled": enabled,
                "scope": "group",
                "ok": True,
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.post("/user")
    async def set_user_switch(
        user_id: str,
        feature: str,
        enabled: bool,
        _: None = Depends(require_superuser),
    ) -> dict[str, Any]:
        """设置用户级开关覆盖

        参数:
            user_id: 用户ID
            feature: 功能名
            enabled: 是否启用

        返回:
            dict: 操作结果
        """
        try:
            ok = runtime_switch.set_user(
                user_id, feature, enabled
            )
            if not ok:
                raise HTTPException(
                    status_code=400,
                    detail=f"参数无效: {user_id}/{feature}",
                )
            return {
                "user_id": user_id,
                "feature": feature,
                "enabled": enabled,
                "scope": "user",
                "ok": True,
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.delete("/group")
    async def clear_group_switch(
        group_id: str,
        feature: str,
        _: None = Depends(require_superuser),
    ) -> dict[str, Any]:
        """清除群组级覆盖

        参数:
            group_id: 群组ID
            feature: 功能名

        返回:
            dict: 操作结果
        """
        try:
            ok = runtime_switch.clear_group(group_id, feature)
            return {
                "group_id": group_id,
                "feature": feature,
                "cleared": ok,
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.delete("/user")
    async def clear_user_switch(
        user_id: str,
        feature: str,
        _: None = Depends(require_superuser),
    ) -> dict[str, Any]:
        """清除用户级覆盖

        参数:
            user_id: 用户ID
            feature: 功能名

        返回:
            dict: 操作结果
        """
        try:
            ok = runtime_switch.clear_user(user_id, feature)
            return {
                "user_id": user_id,
                "feature": feature,
                "cleared": ok,
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    return router
