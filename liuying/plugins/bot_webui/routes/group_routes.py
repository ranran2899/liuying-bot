"""群组管理路由

提供群组列表查询、权限等级与状态修改、超级群组切换。
"""

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from liuying.models._group import GroupConsole

from ..deps import require_auth

__all__ = ["build_group_router"]


def _group_to_view(group: GroupConsole) -> dict[str, Any]:
    """将 GroupConsole 转为视图字典"""
    return {
        "group_id": group.group_id,
        "channel_id": group.channel_id,
        "group_name": group.group_name or "",
        "member_count": group.member_count or 0,
        "max_member_count": group.max_member_count or 0,
        "status": group.status,
        "level": group.level,
        "is_super": group.is_super,
        "platform": group.platform or "qq",
        "proactive_allowed": group.proactive_allowed,
    }


def build_group_router() -> APIRouter:
    """构建群组管理路由

    Returns:
        APIRouter: 群组管理路由器
    """
    router = APIRouter(prefix="/groups", tags=["本体-群组管理"])

    @router.get("")
    async def list_groups(
        status: bool | None = None,
        platform: str = "",
    ) -> dict[str, Any]:
        """获取群组列表

        参数:
            status: 状态过滤（True启用 False禁用 None全部）
            platform: 平台过滤
        """
        try:
            query = GroupConsole.filter()
            if status is not None:
                query = query.filter(status=status)
            if platform:
                query = query.filter(platform=platform)
            groups = await query.all()
            return {
                "groups": [_group_to_view(g) for g in groups],
                "count": len(groups),
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.post("/level")
    async def set_group_level(
        body: dict = Body(default_factory=dict),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """设置群组权限等级

        请求体:
            group_id: 群号
            level: 权限等级（0-10）
        """
        group_id = str(body.get("group_id", "")).strip()
        try:
            level = int(body.get("level", 5))
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400, detail="level 必须为整数"
            )
        if not group_id:
            raise HTTPException(
                status_code=400, detail="group_id 不能为空"
            )
        if not 0 <= level <= 10:
            raise HTTPException(
                status_code=400, detail="level 范围 0-10"
            )
        try:
            await GroupConsole.set_group_level(group_id, level)
            return {"ok": True, "group_id": group_id, "level": level}
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.post("/status")
    async def set_group_status(
        body: dict = Body(default_factory=dict),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """设置群组状态（启用/禁用）

        请求体:
            group_id: 群号
            status: 状态
        """
        group_id = str(body.get("group_id", "")).strip()
        status = bool(body.get("status", True))
        if not group_id:
            raise HTTPException(
                status_code=400, detail="group_id 不能为空"
            )
        try:
            await GroupConsole.set_status(group_id, status)
            return {
                "ok": True,
                "group_id": group_id,
                "status": status,
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.post("/super")
    async def toggle_super_group(
        body: dict = Body(default_factory=dict),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """切换超级群组状态

        请求体:
            group_id: 群号
        """
        group_id = str(body.get("group_id", "")).strip()
        if not group_id:
            raise HTTPException(
                status_code=400, detail="group_id 不能为空"
            )
        try:
            await GroupConsole.toggle_super_group(group_id)
            group = await GroupConsole.get_group(group_id)
            return {
                "ok": True,
                "group_id": group_id,
                "is_super": group.is_super if group else False,
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.post("/proactive")
    async def set_proactive(
        body: dict = Body(default_factory=dict),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """设置群聊主动消息允许状态

        请求体:
            group_id: 群号
            allowed: 是否允许主动消息
        """
        group_id = str(body.get("group_id", "")).strip()
        allowed = bool(body.get("allowed", True))
        if not group_id:
            raise HTTPException(
                status_code=400, detail="group_id 不能为空"
            )
        try:
            await GroupConsole.set_proactive_status(group_id, allowed)
            return {
                "ok": True,
                "group_id": group_id,
                "proactive_allowed": allowed,
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    return router
