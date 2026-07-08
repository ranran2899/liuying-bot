"""本体 WebUI 主应用

聚合所有子路由，挂载静态资源，构建统一的 WebUI 入口路由器。
路由前缀由配置 WEBUI_ROUTE_PREFIX 控制（默认 /bot）。
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from .routes import (
    build_bot_router,
    build_group_router,
    build_health_router,
    build_log_router,
    build_plugin_router,
    build_stats_router,
    build_status_router,
    build_system_router,
    build_task_router,
)

__all__ = ["build_webui_router"]

_STATIC_ROOT = Path(__file__).resolve().parent / "static"
"""静态资源根目录"""

_STATIC_INDEX_PATH = _STATIC_ROOT / "index.html"
"""前端入口HTML路径"""

_STATIC_CONTENT_TYPES: dict[str, str] = {
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}
"""静态资源MIME类型映射"""


def _load_index_html() -> str:
    """加载前端入口HTML

    Returns:
        str: HTML内容
    """
    return _STATIC_INDEX_PATH.read_text(encoding="utf-8")


def _serve_static_asset(filename: str) -> FileResponse:
    """安全地提供静态资源

    校验文件名无路径穿越后返回静态资源。

    参数:
        filename: 文件名

    返回:
        FileResponse: 文件响应

    异常:
        HTTPException: 文件不存在或路径非法时 404
    """
    if Path(filename).name != filename:
        raise HTTPException(
            status_code=404, detail="静态资源不存在"
        )
    target = (_STATIC_ROOT / filename).resolve()
    try:
        target.relative_to(_STATIC_ROOT.resolve())
    except ValueError as exc:
        raise HTTPException(
            status_code=404, detail="静态资源不存在"
        ) from exc
    media_type = _STATIC_CONTENT_TYPES.get(target.suffix.lower())
    if media_type is None or not target.is_file():
        raise HTTPException(
            status_code=404, detail="静态资源不存在"
        )
    return FileResponse(target, media_type=media_type)


def build_webui_router(prefix: str = "/bot") -> APIRouter:
    """构建本体 WebUI 主路由器

    聚合所有子路由，挂载静态资源与入口页。

    参数:
        prefix: 路由前缀（默认 /bot）

    返回:
        APIRouter: WebUI主路由器
    """
    router = APIRouter(prefix=prefix, tags=["WebUI"])

    # 挂载各功能子路由
    router.include_router(build_health_router())
    router.include_router(build_status_router())
    router.include_router(build_system_router())
    router.include_router(build_bot_router())
    router.include_router(build_plugin_router())
    router.include_router(build_group_router())
    router.include_router(build_task_router())
    router.include_router(build_log_router())
    router.include_router(build_stats_router())

    # 入口页与静态资源
    _index_html = _load_index_html()

    @router.get("", response_class=HTMLResponse)
    @router.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        """WebUI入口页"""
        return HTMLResponse(_index_html)

    @router.get("/static/{filename}")
    async def static_asset(filename: str) -> FileResponse:
        """静态资源服务"""
        return _serve_static_asset(filename)

    return router
