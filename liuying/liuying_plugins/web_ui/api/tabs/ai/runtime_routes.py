"""AI 运行时开关路由

提供AI插件功能开关的状态查询与全局/群组/用户级覆盖管理。
POST操作统一使用SwitchUpdateRequest请求体，避免query参数传递问题。
"""

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from liuying.liuying_plugins.AI.core.runtime import runtime_switch

from ....base_model import Result
from ....utils import authentication
from .model import SwitchUpdateRequest

router = APIRouter(prefix="/ai/runtime", dependencies=[authentication()])


@router.get(
    "",
    response_model=Result[dict[str, Any]],
    response_class=JSONResponse,
    description="获取运行时开关状态",
)
async def _(user_id: str = "", group_id: str = "") -> Result[dict[str, Any]]:
    """获取运行时开关状态

    参数:
        user_id: 用户ID（可选）
        group_id: 群组ID（可选）

    返回:
        Result[dict]: 各功能开关状态
    """
    statuses = runtime_switch.get_status(
        user_id=user_id or None,
        group_id=group_id or None,
    )
    return Result.ok(
        {
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
    )


@router.post(
    "/global",
    response_model=Result[dict[str, Any]],
    response_class=JSONResponse,
    description="设置全局开关",
)
async def _(body: SwitchUpdateRequest) -> Result[dict[str, Any]]:
    """设置全局开关"""
    if not runtime_switch.set_global(body.feature, body.enabled):
        return Result.fail(f"未知功能: {body.feature}")
    return Result.ok(
        {
            "feature": body.feature,
            "enabled": body.enabled,
            "scope": "global",
        },
        "全局开关已更新",
    )


@router.post(
    "/group",
    response_model=Result[dict[str, Any]],
    response_class=JSONResponse,
    description="设置群组级开关覆盖",
)
async def _(body: SwitchUpdateRequest) -> Result[dict[str, Any]]:
    """设置群组级开关覆盖"""
    if not body.group_id:
        return Result.fail("group_id 不能为空")
    if not runtime_switch.set_group(
        body.group_id, body.feature, body.enabled
    ):
        return Result.fail(
            f"参数无效: {body.group_id}/{body.feature}"
        )
    return Result.ok(
        {
            "group_id": body.group_id,
            "feature": body.feature,
            "enabled": body.enabled,
            "scope": "group",
        },
        "群组开关已更新",
    )


@router.post(
    "/user",
    response_model=Result[dict[str, Any]],
    response_class=JSONResponse,
    description="设置用户级开关覆盖",
)
async def _(body: SwitchUpdateRequest) -> Result[dict[str, Any]]:
    """设置用户级开关覆盖"""
    if not body.user_id:
        return Result.fail("user_id 不能为空")
    if not runtime_switch.set_user(
        body.user_id, body.feature, body.enabled
    ):
        return Result.fail(
            f"参数无效: {body.user_id}/{body.feature}"
        )
    return Result.ok(
        {
            "user_id": body.user_id,
            "feature": body.feature,
            "enabled": body.enabled,
            "scope": "user",
        },
        "用户开关已更新",
    )


@router.delete(
    "/group",
    response_model=Result[dict[str, Any]],
    response_class=JSONResponse,
    description="清除群组级覆盖",
)
async def _(group_id: str, feature: str) -> Result[dict[str, Any]]:
    """清除群组级覆盖"""
    cleared = runtime_switch.clear_group(group_id, feature)
    return Result.ok(
        {"group_id": group_id, "feature": feature, "cleared": cleared}
    )


@router.delete(
    "/user",
    response_model=Result[dict[str, Any]],
    response_class=JSONResponse,
    description="清除用户级覆盖",
)
async def _(user_id: str, feature: str) -> Result[dict[str, Any]]:
    """清除用户级覆盖"""
    cleared = runtime_switch.clear_user(user_id, feature)
    return Result.ok(
        {"user_id": user_id, "feature": feature, "cleared": cleared}
    )
