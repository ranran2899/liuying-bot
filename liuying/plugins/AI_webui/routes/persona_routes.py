"""人格管理路由

提供AI插家人格列表、用户级人格切换与查询接口。
"""

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from liuying.liuying_plugins.AI.core.persona import persona_manager

from ..deps import require_superuser

__all__ = ["build_persona_router"]


def build_persona_router() -> APIRouter:
    """构建人格管理路由

    Returns:
        APIRouter: 人格管理路由器
    """
    router = APIRouter(prefix="/persona", tags=["AI-人格管理"])

    @router.get("")
    async def list_personas() -> dict[str, Any]:
        """列出所有可用人格及描述

        返回:
            dict: 人格列表
        """
        try:
            personas = persona_manager.list_personas_with_desc()
            return {
                "count": len(personas),
                "personas": personas,
                "active": persona_manager.get_active_persona_name(),
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.get("/{user_id}")
    async def user_persona_info(user_id: str) -> dict[str, Any]:
        """获取用户当前人格配置

        参数:
            user_id: 用户ID

        返回:
            dict: 用户人格信息
        """
        try:
            name = await persona_manager.get_user_persona_name(user_id)
            config = await persona_manager.get_user_persona_config(user_id)
            return {
                "user_id": user_id,
                "persona_name": name,
                "display_name": config.get("name", name),
                "description": persona_manager._extract_persona_desc(
                    config
                ),
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.post("/switch")
    async def switch_user_persona(
        body: dict = Body(default_factory=dict),
        _: None = Depends(require_superuser),
    ) -> dict[str, Any]:
        """切换用户级人格（管理员操作）

        参数:
            body: 包含 user_id 和 persona_name 的请求体

        返回:
            dict: 操作结果
        """
        user_id = str(body.get("user_id", "")).strip()
        persona_name = str(body.get("persona_name", "")).strip()
        if not user_id or not persona_name:
            raise HTTPException(
                status_code=400,
                detail="user_id 和 persona_name 不能为空",
            )
        try:
            await persona_manager.set_user_persona(user_id, persona_name)
            return {
                "ok": True,
                "user_id": user_id,
                "persona_name": persona_name,
            }
        except FileNotFoundError as e:
            raise HTTPException(
                status_code=404, detail=str(e)
            ) from e
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.post("/global")
    async def set_global_persona(
        body: dict = Body(default_factory=dict),
        _: None = Depends(require_superuser),
    ) -> dict[str, Any]:
        """切换全局默认人格（管理员操作）

        参数:
            body: 包含 persona_name 的请求体

        返回:
            dict: 操作结果
        """
        persona_name = str(body.get("persona_name", "")).strip()
        if not persona_name:
            raise HTTPException(
                status_code=400,
                detail="persona_name 不能为空",
            )
        try:
            persona_manager.set_active_persona(persona_name)
            return {
                "ok": True,
                "persona_name": persona_name,
                "scope": "global",
            }
        except FileNotFoundError as e:
            raise HTTPException(
                status_code=404, detail=str(e)
            ) from e
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    return router
