"""AI WebUI 鉴权依赖

提供超级用户校验、运行时上下文管理等共享依赖。
所有写操作路由通过 FastAPI Depends 挂载 _require_superuser。
"""

from dataclasses import dataclass, field

from fastapi import HTTPException
from nonebot import get_driver

from liuying.utils.log import logger

__all__ = [
    "WebUIContext",
    "get_runtime_context",
    "register_runtime_context",
    "require_superuser",
]


@dataclass(slots=True)
class WebUIContext:
    """WebUI运行时上下文

    Attributes:
        enabled: 是否启用
        superusers: 超级用户集合
        route_prefix: 路由前缀
    """

    enabled: bool = True
    superusers: set[str] = field(default_factory=set)
    route_prefix: str = "/ai"


_RUNTIME_CONTEXT: WebUIContext | None = None
"""运行时上下文单例（None表示未初始化）"""


def register_runtime_context(
    *,
    enabled: bool = True,
    superusers: set[str] | None = None,
    route_prefix: str = "/ai",
) -> None:
    """注册WebUI运行时上下文

    Args:
        enabled: 是否启用
        superusers: 超级用户集合
        route_prefix: 路由前缀
    """
    global _RUNTIME_CONTEXT
    _RUNTIME_CONTEXT = WebUIContext(
        enabled=enabled,
        superusers=set(superusers or set()),
        route_prefix=route_prefix or "/ai",
    )
    logger.debug(
        f"AI WebUI上下文已注册: enabled={enabled}, prefix={route_prefix}",
        command="AI-WebUI",
    )


def get_runtime_context() -> WebUIContext:
    """获取运行时上下文

    Returns:
        WebUIContext: 运行时上下文

    Raises:
        RuntimeError: 未初始化
    """
    if _RUNTIME_CONTEXT is None:
        raise RuntimeError("AI WebUI未初始化，请先调用register_runtime_context")
    return _RUNTIME_CONTEXT


def _get_superusers() -> set[str]:
    """获取超级用户集合

    优先使用已注册的运行时上下文，回退到NoneBot driver配置。

    Returns:
        set[str]: 超级用户ID集合
    """
    if _RUNTIME_CONTEXT is not None:
        return _RUNTIME_CONTEXT.superusers
    driver = get_driver()
    return set(getattr(driver.config, "superusers", set()) or set())


def require_superuser(auth_uid: str = "") -> None:
    """写操作鉴权依赖

    校验请求方是否为超级用户，未授权时抛出 401/403。
    通过 FastAPI Depends 挂载到所有写操作路由。

    参数名使用 auth_uid 而非 user_id，避免与 /runtime/user、
    /memory/clear 等路由自身的 user_id 业务参数同名冲突。

    Args:
        auth_uid: 请求方（操作者）用户ID（query参数）

    Raises:
        HTTPException: 缺少参数时 401，非超级用户时 403
    """
    if not auth_uid:
        raise HTTPException(
            status_code=401,
            detail="缺少 auth_uid 参数",
        )
    if str(auth_uid) not in _get_superusers():
        raise HTTPException(
            status_code=403,
            detail="需要超级用户权限",
        )
