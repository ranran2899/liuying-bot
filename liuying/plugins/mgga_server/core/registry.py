"""包路由注册表与生命周期钩子。

各业务模块通过装饰器把处理函数挂到全局注册表上，接入层统一派发::

    from ..core import Packet, Session, on_packet

    @on_packet("lobby.join", auth=True)
    async def _(session: Session, packet: Packet) -> None:
        ...
"""

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from liuying.utils.log import logger

from .protocol import Code, Packet, ProtocolError

if TYPE_CHECKING:
    from .session import Session

type Handler = Callable[["Session", Packet], Awaitable[None]]
type Hook = Callable[["Session"], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class Route:
    """一条包路由。"""

    type: str
    handler: Handler
    auth: bool
    plugin: str


_routes: dict[str, Route] = {}
_on_connect: list[Hook] = []
_on_disconnect: list[Hook] = []


def _caller_plugin(func: Handler) -> str:
    """推断处理函数所属的业务模块名，仅用于日志。

    参数:
        func: 处理函数。

    返回:
        str: 模块短名，如 ``lobby``、``match``。
    """
    module = inspect.getmodule(func)
    if module is None:
        return "?"
    parts = [p for p in module.__name__.split(".") if p != "__init__"]
    return parts[-1] if parts else "?"


def on_packet(packet_type: str, *, auth: bool = True) -> Callable[[Handler], Handler]:
    """注册一个包处理器。

    参数:
        packet_type: 包类型，如 ``"lobby.join"``。
        auth: 是否要求会话已登录，未登录时自动回 ``NOT_AUTHED``。

    返回:
        Callable[[Handler], Handler]: 装饰器。
    """

    def decorator(func: Handler) -> Handler:
        if (exist := _routes.get(packet_type)) is not None:
            raise RuntimeError(f"包类型 {packet_type} 已被 {exist.plugin} 注册")
        plugin = _caller_plugin(func)
        _routes[packet_type] = Route(packet_type, func, auth, plugin)
        logger.debug(f"[mgga_server] 注册包路由 {packet_type} <- {plugin}")
        return func

    return decorator


def on_session_connect(func: Hook) -> Hook:
    """注册会话建立钩子。

    参数:
        func: 钩子函数。

    返回:
        Hook: 原函数。
    """
    _on_connect.append(func)
    return func


def on_session_disconnect(func: Hook) -> Hook:
    """注册会话断开钩子，用于各模块清理自己的引用。

    参数:
        func: 钩子函数。

    返回:
        Hook: 原函数。
    """
    _on_disconnect.append(func)
    return func


def get_route(packet_type: str) -> Route:
    """查路由。

    参数:
        packet_type: 包类型。

    返回:
        Route: 路由对象。

    抛出:
        ProtocolError: 包类型未注册。
    """
    if (route := _routes.get(packet_type)) is None:
        raise ProtocolError(Code.UNKNOWN_TYPE, f"未知包类型 {packet_type}")
    return route


def all_routes() -> dict[str, Route]:
    """返回全部路由的浅拷贝。

    返回:
        dict[str, Route]: 路由表。
    """
    return dict(_routes)


async def _fire(hooks: list[Hook], session: "Session", label: str) -> None:
    """顺序执行钩子，单个钩子异常不影响其它模块。

    参数:
        hooks: 钩子列表。
        session: 会话。
        label: 日志标签。
    """
    for hook in hooks:
        # 各业务模块的钩子相互独立，任一失败都不应中断整条清理链
        try:
            await hook(session)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[mgga_server] {label}钩子异常", e=exc)


async def fire_connect(session: "Session") -> None:
    """触发连接钩子。

    参数:
        session: 会话。
    """
    await _fire(_on_connect, session, "连接")


async def fire_disconnect(session: "Session") -> None:
    """触发断线钩子。

    参数:
        session: 会话。
    """
    await _fire(_on_disconnect, session, "断线")
