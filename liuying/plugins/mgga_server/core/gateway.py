"""WebSocket 接入层：握手、收包、派发、断线清理。"""

from __future__ import annotations

import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from nonebot.log import logger

from .config import GameConfig
from .protocol import PROTOCOL_VERSION, Code, Packet, ProtocolError
from .registry import all_routes, fire_connect, fire_disconnect, get_route
from .session import Session, hub


def install(app: FastAPI, config: GameConfig) -> None:
    """把游戏 WebSocket 路由挂到 NoneBot 的 FastAPI 实例上。"""

    @app.websocket(config.game_ws_path)
    async def _game_endpoint(ws: WebSocket) -> None:  # pragma: no cover - I/O
        await _serve(ws, config)

    # 独立命名空间，避免与机器人自身的 Web API 冲突
    @app.get(config.game_ws_path.rstrip("/") + "/status")
    async def _status() -> dict[str, object]:
        return {
            "protocol": PROTOCOL_VERSION,
            "online": hub.online_count,
            "connections": len(hub.all()),
            "routes": sorted(all_routes().keys()),
        }

    logger.info(f"[mgga_server] 游戏网关已挂载于 ws://<host>{config.game_ws_path}")


async def _serve(ws: WebSocket, config: GameConfig) -> None:
    await ws.accept()
    session = Session(ws)
    session.last_seen = time.monotonic()
    hub.add(session)
    logger.info(f"[mgga_server] 新连接 {session}")

    await session.send("hello", {
        "protocol": PROTOCOL_VERSION,
        "lobby_capacity": config.game_lobby_capacity,
        "tick_rate": config.game_lobby_tick_rate,
        "match_capacity": config.game_match_capacity,
    })
    await fire_connect(session)

    try:
        while True:
            raw = await ws.receive_text()
            session.last_seen = time.monotonic()
            await _dispatch(session, raw)
            if not session.alive:
                break
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.exception(f"[mgga_server] {session} 连接异常")
    finally:
        session.alive = False
        await fire_disconnect(session)
        hub.remove(session)
        logger.info(f"[mgga_server] 断开 {session}")


async def _dispatch(session: Session, raw: str) -> None:
    seq: int | None = None
    ptype = ""
    try:
        packet = Packet.decode(raw)
        seq, ptype = packet.seq, packet.type
        route = get_route(ptype)
        if route.auth and not session.authed:
            raise ProtocolError(Code.NOT_AUTHED, "请先登录")
        await route.handler(session, packet)
    except ProtocolError as err:
        await session.send_error(err.code, err.msg, ptype, seq)
    except Exception:  # noqa: BLE001
        logger.exception(f"[mgga_server] 处理 {ptype} 失败")
        await session.send_error(Code.INTERNAL, "服务器内部错误", ptype, seq)
