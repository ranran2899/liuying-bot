"""包路由注册表与生命周期钩子。

各业务插件通过装饰器把处理函数挂到全局注册表上，`gs_core` 的接入层统一派发：

    from ..core import on_packet, Session, Packet

    @on_packet("lobby.join", auth=True)
    async def _(session: Session, packet: Packet) -> None:
        ...
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from nonebot.log import logger

from .protocol import Code, Packet, ProtocolError

if TYPE_CHECKING:
    from .session import Session

Handler = Callable[["Session", Packet], Awaitable[None]]
Hook = Callable[["Session"], Awaitable[None]]


@dataclass(slots=True)
class Route:
    type: str
    handler: Handler
    auth: bool
    plugin: str


_routes: dict[str, Route] = {}
_on_connect: list[Hook] = []
_on_disconnect: list[Hook] = []


def on_packet(packet_type: str, *, auth: bool = True) -> Callable[[Handler], Handler]:
    """注册一个包处理器。

    Args:
        packet_type: 包类型，如 ``"lobby.join"``。
        auth: 是否要求会话已登录。未登录时自动回 ``NOT_AUTHED``。
    """

    def decorator(func: Handler) -> Handler:
        if packet_type in _routes:
            raise RuntimeError(f"包类型 {packet_type} 已被 {_routes[packet_type].plugin} 注册")
        plugin = _caller_plugin(func)
        _routes[packet_type] = Route(packet_type, func, auth, plugin)
        logger.debug(f"[mgga_server] 注册包路由 {packet_type} <- {plugin}")
        return func

    return decorator


def on_session_connect(func: Hook) -> Hook:
    """会话建立（WebSocket 握手完成）后调用。"""
    _on_connect.append(func)
    return func


def on_session_disconnect(func: Hook) -> Hook:
    """会话断开时调用，用于各插件清理自己的引用。"""
    _on_disconnect.append(func)
    return func


def get_route(packet_type: str) -> Route:
    route = _routes.get(packet_type)
    if route is None:
        raise ProtocolError(Code.UNKNOWN_TYPE, f"未知包类型 {packet_type}")
    return route


def all_routes() -> dict[str, Route]:
    return dict(_routes)


async def fire_connect(session: "Session") -> None:
    for hook in _on_connect:
        await hook(session)


async def fire_disconnect(session: "Session") -> None:
    for hook in _on_disconnect:
        try:
            await hook(session)
        except Exception:  # noqa: BLE001 - 清理钩子失败不应影响其它插件
            logger.exception("[mgga_server] 断线钩子异常")


def _caller_plugin(func: Handler) -> str:
    module = inspect.getmodule(func)
    return module.__name__.split(".")[0] if module else "?"
