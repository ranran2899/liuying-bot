"""AI 人格管理路由

提供AI插家人格列表、用户级人格切换与查询接口。
"""

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from liuying.liuying_plugins.AI.core.persona import persona_manager

from ....base_model import Result
from ....utils import authentication
from .model import GlobalPersonaRequest, PersonaSwitchRequest

router = APIRouter(prefix="/ai/persona", dependencies=[authentication()])


@router.get(
    "",
    response_model=Result[dict[str, Any]],
    response_class=JSONResponse,
    description="列出所有人格",
)
async def _() -> Result[dict[str, Any]]:
    """列出所有可用人格及描述"""
    personas = persona_manager.list_personas_with_desc()
    return Result.ok(
        {
            "count": len(personas),
            "personas": personas,
            "active": persona_manager.get_active_persona_name(),
        }
    )


@router.get(
    "/{user_id}",
    response_model=Result[dict[str, Any]],
    response_class=JSONResponse,
    description="获取用户人格配置",
)
async def _(user_id: str) -> Result[dict[str, Any]]:
    """获取用户当前人格配置"""
    name = await persona_manager.get_user_persona_name(user_id)
    config = await persona_manager.get_user_persona_config(user_id)
    return Result.ok(
        {
            "user_id": user_id,
            "persona_name": name,
            "display_name": config.get("name", name),
            "description": config.get("description", ""),
        }
    )


@router.post(
    "/switch",
    response_model=Result[dict[str, Any]],
    response_class=JSONResponse,
    description="切换用户级人格",
)
async def _(body: PersonaSwitchRequest) -> Result[dict[str, Any]]:
    """切换用户级人格"""
    if not body.user_id or not body.persona_name:
        return Result.fail("user_id 和 persona_name 不能为空")
    try:
        await persona_manager.set_user_persona(
            body.user_id, body.persona_name
        )
    except FileNotFoundError as e:
        return Result.fail(str(e))
    return Result.ok(
        {
            "ok": True,
            "user_id": body.user_id,
            "persona_name": body.persona_name,
        },
        "人格已切换",
    )


@router.post(
    "/global",
    response_model=Result[dict[str, Any]],
    response_class=JSONResponse,
    description="切换全局默认人格",
)
async def _(body: GlobalPersonaRequest) -> Result[dict[str, Any]]:
    """切换全局默认人格"""
    if not body.persona_name:
        return Result.fail("persona_name 不能为空")
    try:
        persona_manager.set_active_persona(body.persona_name)
    except FileNotFoundError as e:
        return Result.fail(str(e))
    return Result.ok(
        {"ok": True, "persona_name": body.persona_name, "scope": "global"},
        "全局人格已切换",
    )
