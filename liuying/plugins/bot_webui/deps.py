"""本体 WebUI 鉴权依赖

提供账号+令牌校验、运行时上下文管理等共享依赖。
所有写操作路由通过 FastAPI Depends 挂载 require_auth。
"""

import hmac
from dataclasses import dataclass

from fastapi import HTTPException

from liuying.utils.log import logger

from .config import get_config

__all__ = [
    "WebUIContext",
    "get_runtime_context",
    "register_runtime_context",
    "require_auth",
]


@dataclass(slots=True)
class WebUIContext:
    """本体 WebUI 运行时上下文

    Attributes:
        enabled: 是否启用
        account: 登录账号
        token: 登录令牌
        route_prefix: 路由前缀
    """

    enabled: bool = True
    account: str = ""
    token: str = ""
    route_prefix: str = "/bot"


_RUNTIME_CONTEXT: WebUIContext | None = None
"""运行时上下文单例（None表示未初始化）"""


def register_runtime_context(
    *,
    enabled: bool = True,
    account: str = "",
    token: str = "",
    route_prefix: str = "/bot",
) -> None:
    """注册本体 WebUI 运行时上下文

    Args:
        enabled: 是否启用
        account: 登录账号
        token: 登录令牌
        route_prefix: 路由前缀
    """
    global _RUNTIME_CONTEXT
    _RUNTIME_CONTEXT = WebUIContext(
        enabled=enabled,
        account=account,
        token=token,
        route_prefix=route_prefix or "/bot",
    )
    logger.debug(
        f"本体 WebUI 上下文已注册: enabled={enabled}, prefix={route_prefix}",
        command="WebUI",
    )


def get_runtime_context() -> WebUIContext:
    """获取运行时上下文

    Returns:
        WebUIContext: 运行时上下文

    Raises:
        RuntimeError: 未初始化
    """
    if _RUNTIME_CONTEXT is None:
        raise RuntimeError("本体 WebUI 未初始化，请先调用register_runtime_context")
    return _RUNTIME_CONTEXT


def _get_credentials() -> tuple[str, str]:
    """获取登录账号与令牌

    优先使用已注册的运行时上下文，回退到配置读取。

    Returns:
        tuple[str, str]: (账号, 令牌)
    """
    if _RUNTIME_CONTEXT is not None:
        return _RUNTIME_CONTEXT.account, _RUNTIME_CONTEXT.token
    account = str(get_config("WEBUI_ACCOUNT", "admin") or "admin")
    token = str(get_config("WEBUI_TOKEN", "") or "")
    return account, token


def require_auth(account: str = "", token: str = "") -> None:
    """写操作鉴权依赖

    校验请求方提供的账号与令牌是否匹配配置，未授权时抛出 401/403。
    通过 FastAPI Depends 挂载到所有写操作路由。

    参数名使用 account/token 而非 user_id 等，避免与路由自身的业务参数同名冲突。

    Args:
        account: 请求方提供的账号（query参数）
        token: 请求方提供的令牌（query参数）

    Raises:
        HTTPException: 缺少参数时 401，账号或令牌不匹配时 403
    """
    if not account or not token:
        raise HTTPException(
            status_code=401,
            detail="缺少 account 或 token 参数",
        )
    expected_account, expected_token = _get_credentials()
    if not expected_token:
        raise HTTPException(
            status_code=403,
            detail="服务端未配置 WEBUI_TOKEN，无法鉴权",
        )
    if not (
        hmac.compare_digest(account, expected_account)
        and hmac.compare_digest(token, expected_token)
    ):
        raise HTTPException(
            status_code=403,
            detail="账号或令牌错误",
        )
