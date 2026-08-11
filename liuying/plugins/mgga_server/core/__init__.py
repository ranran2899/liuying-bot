"""core —— 游戏服务器核心模块（猛鬼公寓 · liuying-bot 插件）。

提供给其它插件的公共设施：

* :class:`Packet` / :class:`ProtocolError` / :class:`Code`  —— 协议与错误码
* :class:`Session` / :data:`hub`                            —— 会话与在线表
* :func:`on_packet` / :func:`on_session_disconnect`         —— 包路由与生命周期钩子
* :data:`config`                                            —— 服务器配置

本模块只负责 WebSocket 接入与派发，不含任何玩法逻辑；玩法（auth / lobby / match）
以子模块形式挂载，新增玩法只需 `@on_packet("x.y")`，无需改动网关。
"""

from __future__ import annotations

import asyncio
import time

from nonebot import get_app, get_driver
from nonebot.log import logger

from .config import GameConfig, load_config
from .protocol import PROTOCOL_VERSION, Code, Packet, ProtocolError
from .registry import (
    on_packet,
    on_session_connect,
    on_session_disconnect,
)
from .session import Session, SessionHub, hub

__all__ = [
    "PROTOCOL_VERSION",
    "Code",
    "GameConfig",
    "Packet",
    "ProtocolError",
    "Session",
    "SessionHub",
    "config",
    "hub",
    "on_packet",
    "on_session_connect",
    "on_session_disconnect",
]

#: 全局配置对象。导入期先取默认值，启动时再用 liuying 配置就地刷新
#: （保持对象 id 不变，其它模块 `from ..core import config` 后可直接看到新值）。
config: GameConfig = load_config()

_driver = get_driver()
_heartbeat_task: asyncio.Task | None = None


@_driver.on_startup
async def _startup() -> None:
    global _heartbeat_task
    from . import gateway

    # 插件元数据注册完成后，liuying 的配置才可读，这里就地刷新
    config.__dict__.update(load_config().__dict__)

    gateway.install(get_app(), config)
    _heartbeat_task = asyncio.create_task(_heartbeat_loop())
    logger.info(
        f"[猛鬼公寓] 游戏服务器已挂载于 {config.game_ws_path}"
        f"（单线 {config.game_lobby_capacity} 人）"
    )


@_driver.on_shutdown
async def _shutdown() -> None:
    if _heartbeat_task is not None:
        _heartbeat_task.cancel()
    for session in hub.all():
        await session.close("服务器关闭")


async def _heartbeat_loop() -> None:
    """定期清理长时间无任何数据包的僵尸连接。"""
    timeout = config.game_heartbeat_timeout
    while True:
        await asyncio.sleep(timeout / 2.0)
        now = time.monotonic()
        for session in hub.all():
            if now - session.last_seen > timeout:
                logger.info(f"[猛鬼公寓] {session} 心跳超时，断开")
                await session.close("心跳超时")


@on_packet("ping", auth=False)
async def _handle_ping(session: Session, packet: Packet) -> None:
    """心跳。客户端每 5 秒发一次，服务端原样回 `pong` 并附服务器时间戳。"""
    await session.send("pong", {"t": packet.data.get("t", 0), "server_ms": int(time.time() * 1000)},
                       packet.seq)
