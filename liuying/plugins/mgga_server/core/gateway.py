"""WebSocket 接入层：握手、收包、限流、派发、断线清理。"""

import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from liuying.utils.log import logger

from .config import GameConfig
from .protocol import PROTOCOL_VERSION, Code, Packet, ProtocolError
from .registry import fire_connect, fire_disconnect, get_route
from .session import Session, hub

#: 防止重复挂载路由（NoneBot 热重载时 on_startup 可能被再次触发）
_installed = False


def install(app: FastAPI, config: GameConfig) -> None:
    """把游戏 WebSocket 路由挂到 NoneBot 的 FastAPI 实例上。

    参数:
        app: FastAPI 实例。
        config: 服务器配置。
    """
    global _installed
    if _installed:
        logger.debug("[mgga_server] 网关已挂载，跳过重复注册")
        return
    _installed = True

    @app.websocket(config.game_ws_path)
    async def _game_endpoint(ws: WebSocket) -> None:
        await _serve(ws, config)

    # 独立命名空间，避免与机器人自身的 Web API 冲突。
    # 只暴露聚合数值，不泄漏具体路由清单，避免给外部探测协议面。
    @app.get(config.game_ws_path.rstrip("/") + "/status")
    async def _status() -> dict[str, object]:
        return {
            "protocol": PROTOCOL_VERSION,
            "online": hub.online_count,
            "connections": hub.conn_count,
        }

    logger.info(f"[mgga_server] 游戏网关已挂载于 ws://<host>{config.game_ws_path}")


async def _serve(ws: WebSocket, config: GameConfig) -> None:
    """服务单条连接的完整生命周期。

    参数:
        ws: WebSocket 连接。
        config: 服务器配置。
    """
    await ws.accept()
    session = Session(ws, packet_rate=config.game_packet_rate)
    hub.add(session)
    logger.info(f"[mgga_server] 新连接 {session}")

    await session.send(
        "hello",
        {
            "protocol": PROTOCOL_VERSION,
            "lobby_capacity": config.game_lobby_capacity,
            "tick_rate": config.game_lobby_tick_rate,
            "match_capacity": config.game_match_capacity,
            "heartbeat": config.game_heartbeat_timeout,
        },
    )
    await fire_connect(session)

    max_bytes = config.game_max_packet_bytes
    # WebSocket 读循环运行在网络边界上，任何异常都必须收敛到 finally 做清理
    try:
        while session.alive:
            raw = await ws.receive_text()
            session.last_seen = time.monotonic()

            if len(raw) > max_bytes:
                await session.send_error(Code.TOO_LARGE, "数据包过大")
                await session.close("数据包过大")
                break
            if not session.limiter.allow():
                await session.send_error(Code.RATE_LIMIT, "请求过于频繁")
                await session.close("请求过于频繁")
                break

            await _dispatch(session, raw)
    except WebSocketDisconnect:
        logger.debug(f"[mgga_server] {session} 客户端主动断开")
    except Exception as exc:  # noqa: BLE001
        logger.error(f"[mgga_server] {session} 连接异常", e=exc)
    finally:
        session.alive = False
        await fire_disconnect(session)
        hub.remove(session)
        logger.info(f"[mgga_server] 断开 {session}")


async def _dispatch(session: Session, raw: str) -> None:
    """解码并派发单个数据包。

    参数:
        session: 会话。
        raw: 原始文本帧。
    """
    seq: int | None = None
    ptype = ""
    # 业务处理器由各模块提供，未预期的异常统一兜底为 INTERNAL，避免拖垮连接
    try:
        packet = Packet.decode(raw)
        seq, ptype = packet.seq, packet.type
        route = get_route(ptype)
        if route.auth and not session.authed:
            raise ProtocolError(Code.NOT_AUTHED, "请先登录")
        await route.handler(session, packet)
    except ProtocolError as err:
        await session.send_error(err.code, err.msg, ptype, seq)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"[mgga_server] 处理 {ptype} 失败", e=exc)
        await session.send_error(Code.INTERNAL, "服务器内部错误", ptype, seq)
