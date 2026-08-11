"""core —— 游戏服务器核心模块（猛鬼公寓 · liuying-bot 插件）。

提供给其它模块的公共设施：

* :class:`Packet` / :class:`ProtocolError` / :class:`Code`  —— 协议与错误码
* :class:`Session` / :data:`hub`                            —— 会话与在线表
* :func:`on_packet` / :func:`on_session_disconnect`         —— 包路由与生命周期钩子
* :data:`config`                                            —— 服务器配置

本模块只负责 WebSocket 接入与派发，不含任何玩法逻辑；玩法（auth / lobby / match）
以子模块形式挂载，新增玩法只需 ``@on_packet("x.y")``，无需改动网关。
"""

import asyncio
import time

from nonebot import get_app

from liuying.utils.log import logger
from liuying.utils.manager import PriorityLifecycle

from .config import GameConfig, load_config
from .protocol import PROTOCOL_VERSION, Code, Packet, ProtocolError
from .registry import (
    all_routes,
    on_packet,
    on_session_connect,
    on_session_disconnect,
)
from .session import RateLimiter, Session, SessionHub, hub

__all__ = [
    "PROTOCOL_VERSION",
    "Code",
    "GameConfig",
    "Packet",
    "ProtocolError",
    "RateLimiter",
    "Session",
    "SessionHub",
    "all_routes",
    "config",
    "hub",
    "on_packet",
    "on_session_connect",
    "on_session_disconnect",
]

#: 全局配置对象。导入期先取默认值，启动时再用 liuying 配置就地刷新
#: （保持对象 id 不变，其它模块 ``from ..core import config`` 后可直接看到新值）。
config: GameConfig = load_config()

_heartbeat_task: asyncio.Task[None] | None = None


# 数据库在 priority=1 初始化，这里排在其后，确保玩法模块可直接读写 ORM
@PriorityLifecycle.on_startup(priority=20)
async def _startup() -> None:
    """挂载网关并启动心跳巡检。"""
    global _heartbeat_task
    from . import gateway

    # 插件元数据注册完成后 liuying 配置才可读，这里就地刷新
    config.refresh()

    gateway.install(get_app(), config)
    _heartbeat_task = asyncio.create_task(_heartbeat_loop())
    logger.info(
        f"[mgga_server] 游戏服务器已挂载于 {config.game_ws_path}"
        f"（单线 {config.game_lobby_capacity} 人，"
        f"{len(all_routes())} 条包路由）"
    )


@PriorityLifecycle.on_shutdown(priority=20)
async def _shutdown() -> None:
    """停止巡检并踢下所有在线连接。"""
    global _heartbeat_task
    if _heartbeat_task is not None:
        _heartbeat_task.cancel()
        _heartbeat_task = None
    await asyncio.gather(
        *(s.close("服务器关闭") for s in hub.all()), return_exceptions=True
    )


async def _heartbeat_loop() -> None:
    """定期清理长时间无任何数据包的僵尸连接。"""
    while True:
        # 每轮重新读取，配置在线调整后无需重启即可生效
        timeout = config.game_heartbeat_timeout
        await asyncio.sleep(max(timeout / 2.0, 1.0))
        # 后台常驻任务：任何异常都不能让循环退出，否则僵尸连接将永不回收
        try:
            now = time.monotonic()
            stale = [s for s in hub.all() if now - s.last_seen > timeout]
            for session in stale:
                logger.info(f"[mgga_server] {session} 心跳超时，断开")
            if stale:
                await asyncio.gather(
                    *(s.close("心跳超时") for s in stale), return_exceptions=True
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("[mgga_server] 心跳巡检异常", e=exc)


@on_packet("ping", auth=False)
async def _handle_ping(session: Session, packet: Packet) -> None:
    """心跳。客户端定期发送，服务端原样回 ``pong`` 并附服务器时间戳。

    参数:
        session: 会话。
        packet: 请求包。
    """
    await session.send(
        "pong",
        {"t": packet.data.get("t", 0), "server_ms": int(time.time() * 1000)},
        packet.seq,
    )
