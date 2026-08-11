"""lobby —— 联机地图大厅与动态分线模块。

协议：

* ``lobby.list``   {}                        -> ``lobby.list`` {lobbies:[...]}
* ``lobby.join``   {id, line}                -> ``lobby.joined`` {...} （line=0 自动分配）
* ``lobby.switch`` {line}                    -> ``lobby.joined``（line=0 自动换到人少的线）
* ``lobby.leave``  {}                        -> ``lobby.left``
* ``lobby.move``   {x, y, dir, moving}       -> 无回包，随下一帧快照广播
* ``lobby.chat``   {text}                    -> 广播 ``lobby.chat``

服务端主动推送：

* ``lobby.enter`` {player}   有人进线
* ``lobby.exit``  {uid}      有人离线/切线
* ``lobby.state`` {ps:[[uid,x,y,dir,moving], ...]}  位置快照（默认 10Hz）
* ``lobby.lines`` {id, lines:[...]}  线路人数变化
"""

from __future__ import annotations

import asyncio
import time

from nonebot import get_driver
from nonebot.log import logger

from ..core import (
    Code,
    Packet,
    ProtocolError,
    Session,
    config,
    hub,
    on_packet,
    on_session_disconnect,
)
from .lobby import Avatar, Line, Lobby, LobbyManager

__all__ = ["Avatar", "Line", "Lobby", "LobbyManager", "manager", "line_of"]

CHAT_MAX_LEN = 80
CHAT_INTERVAL = 1.0

manager = LobbyManager(config.game_lobby_capacity)

_driver = get_driver()
_tick_task: asyncio.Task | None = None


@_driver.on_startup
async def _startup() -> None:
    """注册内置大厅地图并启动同步循环。"""
    global _tick_task
    manager.capacity = config.game_lobby_capacity
    # 三张小地图已合并为一张统一的大校园地图（小学建筑风格 + 大学校园式开阔布局）
    manager.register("campus", "云岭校园", width=3600, height=2400, spawn=(1800, 2150))
    _tick_task = asyncio.create_task(_tick_loop())
    logger.info(f"[mgga_server] 已注册 {len(manager.lobbies)} 张大厅地图，"
                f"单线容量 {manager.capacity}")


@_driver.on_shutdown
async def _shutdown() -> None:
    if _tick_task is not None:
        _tick_task.cancel()


# ---------------------------------------------------------------- 会话状态

def line_of(session: Session) -> Line | None:
    value = session.state.get("lobby_line")
    return value if isinstance(value, Line) else None


def _require_line(session: Session) -> Line:
    line = line_of(session)
    if line is None:
        raise ProtocolError(Code.NOT_IN_LOBBY, "你还没有进入大厅")
    return line


def _avatar_of(session: Session) -> Avatar:
    line = _require_line(session)
    avatar = line.avatars.get(session.uid)
    if avatar is None:
        raise ProtocolError(Code.NOT_IN_LOBBY, "大厅形象丢失，请重新进入")
    return avatar


# ---------------------------------------------------------------- 进出大厅

async def _enter(session: Session, lobby: Lobby, line: Line, seq: int | None) -> None:
    avatar = Avatar(uid=session.uid, name=session.nickname,
                    x=lobby.spawn[0], y=lobby.spawn[1], stamp=int(time.time() * 1000))
    line.members[session.uid] = session
    line.avatars[session.uid] = avatar
    session.state["lobby_line"] = line
    session.state["lobby_id"] = lobby.id

    await session.send("lobby.joined", {
        "id": lobby.id,
        "name": lobby.name,
        "line": line.index,
        "cap": line.capacity,
        "w": lobby.width,
        "h": lobby.height,
        "self": avatar.full(),
        "players": [a.full() for a in line.avatars.values() if a.uid != session.uid],
        "lines": [lobby.lines[i].brief() for i in sorted(lobby.lines)],
    }, seq)

    others = [s for s in line.sessions() if s.uid != session.uid]
    await hub.broadcast(others, "lobby.enter", {"player": avatar.full()})
    await _broadcast_lines(lobby)
    logger.info(f"[mgga_server] {session.nickname} 进入 {lobby.name} {line.index} 线"
                f"（{line.count}/{line.capacity}）")


async def _leave(session: Session, *, notify_self: bool = True, seq: int | None = None) -> None:
    line = line_of(session)
    if line is None:
        return
    line.members.pop(session.uid, None)
    line.avatars.pop(session.uid, None)
    session.state.pop("lobby_line", None)
    lobby = manager.get(line.lobby_id)

    await hub.broadcast(line.sessions(), "lobby.exit", {"uid": session.uid})
    if lobby is not None:
        lobby.prune()
        await _broadcast_lines(lobby)
    if notify_self:
        await session.send("lobby.left", {}, seq)


async def _broadcast_lines(lobby: Lobby) -> None:
    """把线路人数变化推给该大厅内所有玩家（用于分线面板实时刷新）。"""
    payload = {"id": lobby.id, "total": lobby.total,
               "lines": [lobby.lines[i].brief() for i in sorted(lobby.lines)]}
    targets: list[Session] = []
    for line in lobby.lines.values():
        targets.extend(line.sessions())
    await hub.broadcast(targets, "lobby.lines", payload)


# ---------------------------------------------------------------- 包处理

@on_packet("lobby.list")
async def _handle_list(session: Session, packet: Packet) -> None:
    await session.send("lobby.list", {"lobbies": manager.list_brief(),
                                      "online": hub.online_count}, packet.seq)


@on_packet("lobby.join")
async def _handle_join(session: Session, packet: Packet) -> None:
    lobby_id = packet.str_of("id", max_len=32)
    want = packet.int_of("line", 0)
    lobby = manager.get(lobby_id)
    if lobby is None:
        raise ProtocolError(Code.NO_LOBBY, f"大厅 {lobby_id} 不存在")

    await _leave(session, notify_self=False)

    if want <= 0:
        line = lobby.pick_line()
    else:
        line = lobby.ensure_line(want)
        if line.full:
            raise ProtocolError(Code.LINE_FULL,
                                f"{want} 线已满（{line.capacity} 人），请换一条线")
    await _enter(session, lobby, line, packet.seq)


@on_packet("lobby.switch")
async def _handle_switch(session: Session, packet: Packet) -> None:
    current = _require_line(session)
    lobby = manager.get(current.lobby_id)
    if lobby is None:
        raise ProtocolError(Code.NO_LOBBY, "所在大厅已下线")
    want = packet.int_of("line", 0)
    if want == current.index:
        raise ProtocolError(Code.BAD_FIELD, "已经在这条线路上了")

    await _leave(session, notify_self=False)
    if want <= 0:
        target = lobby.pick_line()
    else:
        target = lobby.ensure_line(want)
        if target.full:
            # 切线失败要把玩家放回原线，避免卡在「无大厅」状态
            fallback = lobby.ensure_line(current.index)
            await _enter(session, lobby, fallback, None)
            raise ProtocolError(Code.LINE_FULL, f"{want} 线已满，已留在原线路")
    await _enter(session, lobby, target, packet.seq)


@on_packet("lobby.leave")
async def _handle_leave(session: Session, packet: Packet) -> None:
    await _leave(session, seq=packet.seq)


@on_packet("lobby.move")
async def _handle_move(session: Session, packet: Packet) -> None:
    """位置上报。服务端做边界钳制后写入快照，由 tick 统一广播。"""
    line = _require_line(session)
    lobby = manager.get(line.lobby_id)
    if lobby is None:
        return
    avatar = _avatar_of(session)
    avatar.x = min(max(packet.float_of("x", avatar.x), 0.0), lobby.width)
    avatar.y = min(max(packet.float_of("y", avatar.y), 0.0), lobby.height)
    avatar.dir = min(max(packet.int_of("dir", avatar.dir), 0), 3)
    avatar.moving = bool(packet.data.get("moving", False))
    avatar.stamp = int(time.time() * 1000)
    line.dirty = True


@on_packet("lobby.chat")
async def _handle_chat(session: Session, packet: Packet) -> None:
    line = _require_line(session)
    text = packet.str_of("text", max_len=CHAT_MAX_LEN)
    now = time.monotonic()
    last = float(session.state.get("chat_at", 0.0))
    if now - last < CHAT_INTERVAL:
        raise ProtocolError(Code.RATE_LIMIT, "说得太快了，缓一缓")
    session.state["chat_at"] = now
    await hub.broadcast(line.sessions(), "lobby.chat", {
        "uid": session.uid, "name": session.nickname, "text": text,
        "ms": int(time.time() * 1000),
    })


@on_session_disconnect
async def _on_disconnect(session: Session) -> None:
    await _leave(session, notify_self=False)


# ---------------------------------------------------------------- 同步循环

async def _tick_loop() -> None:
    interval = 1.0 / float(config.game_lobby_tick_rate)
    while True:
        await asyncio.sleep(interval)
        try:
            await _tick_once()
        except asyncio.CancelledError:  # pragma: no cover
            raise
        except Exception:  # noqa: BLE001
            logger.exception("[mgga_server] 同步循环异常")


async def _tick_once() -> None:
    for lobby in manager.lobbies.values():
        for line in lobby.lines.values():
            if not line.dirty or line.count == 0:
                continue
            line.dirty = False
            await hub.broadcast(line.sessions(), "lobby.state",
                                {"ps": [a.snapshot() for a in line.avatars.values()]})
