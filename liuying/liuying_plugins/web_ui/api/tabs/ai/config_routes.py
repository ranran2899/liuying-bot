"""AI 配置管理路由

提供AI插件配置项的脱敏查看与修改。
"""

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ....base_model import Result
from ....utils import authentication
from .data_source import (
    list_config_entries,
    update_config_value,
)
from .model import ConfigValueUpdate

router = APIRouter(prefix="/ai/config", dependencies=[authentication()])


@router.get(
    "",
    response_model=Result[dict[str, Any]],
    response_class=JSONResponse,
    description="获取AI插件配置（脱敏）",
)
async def _() -> Result[dict[str, Any]]:
    """获取AI插件配置（脱敏）

    返回:
        Result[dict]: 配置项列表与分组
    """
    entries, groups = list_config_entries()
    return Result.ok(
        {"entries": entries, "groups": groups},
        "获取配置成功",
    )


@router.post(
    "/value",
    response_model=Result[dict[str, Any]],
    response_class=JSONResponse,
    description="修改单个配置项",
)
async def _(body: ConfigValueUpdate) -> Result[dict[str, Any]]:
    """修改单个配置项

    参数:
        body: 包含 key 和 value 的请求体

    返回:
        Result[dict]: 操作结果
    """
    try:
        result = update_config_value(body.key, body.value)
    except ValueError as e:
        return Result.fail(str(e))
    return Result.ok(result, "配置已更新")
