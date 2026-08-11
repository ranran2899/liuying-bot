"""lobby —— 联机地图大厅与动态分线模块。

协议：

* ``lobby.list``   {}                        -> ``lobby.list`` {lobbies:[...]}
* ``lobby.join``   {id, line}                -> ``lobby.joined``（line=0 自动分配）
* ``lobby.switch`` {line}                    -> ``lobby.joined``（line=0 自动换线）
* ``lobby.leave``  {}                        -> ``lobby.left``
* ``lobby.move``   {x, y, dir, moving}       -> 无回包，随下一帧快照广播
* ``lobby.chat``   {text}                    -> 广播 ``lobby.chat``

服务端主动推送：

* ``lobby.enter`` {player}   有人进线
* ``lobby.exit``  {uid}      有人离线/切线
* ``lobby.state`` {ps:[[uid,x,y,dir,moving], ...]}  位置快照（默认 10Hz）
* ``lobby.lines`` {id, lines:[...]}  线路人数变化
"""

import asyncio
import time

from liuying.utils.log import logger
from liuying.utils.manager import PriorityLifecycle

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

__all__ = ["Avatar", "Line", "Lobby", "LobbyManager", "line_of", "manager"]

#: 聊天单条长度上限
CHAT_MAX_LEN = 80
#: 聊天最小间隔（秒）
CHAT_INTERVAL = 1.0
#: 会话状态键
KEY_LINE = "lobby_line"
KEY_LOBBY = "lobby_id"
KEY_CHAT_AT = "chat_at"

manager = LobbyManager()

_tick_task: asyncio.Task[None] | None = None


@PriorityLifecycle.on_startup(priority=21)
async def _startup() -> None:
    """注册内置大厅地图并启动同步循环。"""
    global _tick_task
    # 统一的大校园地图（小学建筑风格 + 大学校园式开阔布局）
    manager.register("campus", "云岭校园", width=3600, height=2400, spawn=(1800, 2150))
    _tick_task = asyncio.create_task(_tick_loop())
    logger.info(
        f"[mgga_server] 已注册 {len(manager.lobbies)} 张大厅地图，"
        f"单线容量 {config.game_lobby_capacity}"
    )


@PriorityLifecycle.on_shutdown(priority=21)
async def _shutdown() -> None:
    """停止同步循环。"""
    global _tick_task
    if _tick_task is not None:
        _tick_task.cancel()
        _tick_task = None


# ---------------------------------------------------------------- 会话状态


def line_of(session: Session) -> Line | None:
    """取会话所在线路。

    参数:
        session: 会话。

    返回:
        Line | None: 所在线路。
    """
    value = session.state.get(KEY_LINE)
    return value if isinstance(value, Line) else None


def _require_line(session: Session) -> tuple[Lobby, Line]:
    """取会话所在的大厅与线路。

    参数:
        session: 会话。

    返回:
        tuple[Lobby, Line]: 大厅与线路。

    抛出:
        ProtocolError: 不在大厅内，或大厅已下线。
    """
    line = line_of(session)
    if line is None:
        raise ProtocolError(Code.NOT_IN_LOBBY, "你还没有进入大厅")
    lobby = manager.get(line.lobby_id)
    if lobby is None:
        raise ProtocolError(Code.NO_LOBBY, "所在大厅已下线")
    return lobby, line


def _avatar_of(session: Session, line: Line) -> Avatar:
    """取会话在指定线路上的形象。

    参数:
        session: 会话。
        line: 线路。

    返回:
        Avatar: 形象对象。

    抛出:
        ProtocolError: 形象缺失。
    """
    if (avatar := line.avatars.get(session.uid)) is None:
        raise ProtocolError(Code.NOT_IN_LOBBY, "大厅形象丢失，请重新进入")
    return avatar


def _resolve_target(lobby: Lobby, want: int) -> Line:
    """把客户端请求的线路号解析成可进入的线路。

    参数:
        lobby: 大厅。
        want: 线路号，``<=0`` 表示自动分配。

    返回:
        Line: 目标线路。

    抛出:
        ProtocolError: 线路号非法或线路已满。
    """
    if want <= 0:
        if (picked := lobby.pick_line()) is None:
            raise ProtocolError(Code.LINE_FULL, "全部线路已满，请稍后再试")
        return picked

    if not lobby.can_open(want):
        raise ProtocolError(Code.BAD_FIELD, f"线路号需在 1~{lobby.max_lines} 之间")
    target = lobby.ensure_line(want)
    if target.full:
        raise ProtocolError(
            Code.LINE_FULL, f"{want} 线已满（{target.capacity} 人），请换一条线"
        )
    return target


# ---------------------------------------------------------------- 进出大厅


async def _enter(session: Session, lobby: Lobby, line: Line, seq: int | None) -> None:
    """把玩家放进指定线路并同步首帧。

    参数:
        session: 会话。
        lobby: 大厅。
        line: 线路。
        seq: 请求序号。
    """
    avatar = Avatar(
        uid=session.uid,
        name=session.nickname,
        x=lobby.spawn[0],
        y=lobby.spawn[1],
        stamp=int(time.time() * 1000),
    )
    line.members[session.uid] = session
    line.avatars[session.uid] = avatar
    line.dirty = True
    session.state[KEY_LINE] = line
    session.state[KEY_LOBBY] = lobby.id

    await session.send(
        "lobby.joined",
        {
            "id": lobby.id,
            "name": lobby.name,
            "line": line.index,
            "cap": line.capacity,
            "w": lobby.width,
            "h": lobby.height,
            "self": avatar.full(),
            "players": [
                a.full() for a in line.avatars.values() if a.uid != session.uid
            ],
            "lines": [lobby.lines[i].brief() for i in sorted(lobby.lines)],
        },
        seq,
    )

    others = [s for s in line.sessions() if s.uid != session.uid]
    await hub.broadcast(others, "lobby.enter", {"player": avatar.full()})
    await _broadcast_lines(lobby)
    logger.debug(
        f"[mgga_server] {session.nickname} 进入 {lobby.name} {line.index} 线"
        f"（{line.count}/{line.capacity}）"
    )


async def _leave(
    session: Session, *, notify_self: bool = True, seq: int | None = None
) -> None:
    """把玩家从当前线路移除。

    参数:
        session: 会话。
        notify_self: 是否给自己回 ``lobby.left``。
        seq: 请求序号。
    """
    if (line := line_of(session)) is None:
        return
    line.members.pop(session.uid, None)
    line.avatars.pop(session.uid, None)
    line.dirty = True
    session.state.pop(KEY_LINE, None)
    session.state.pop(KEY_LOBBY, None)

    await hub.broadcast(line.sessions(), "lobby.exit", {"uid": session.uid})
    if (lobby := manager.get(line.lobby_id)) is not None:
        lobby.prune()
        await _broadcast_lines(lobby)
    if notify_self:
        await session.send("lobby.left", {}, seq)


async def _broadcast_lines(lobby: Lobby) -> None:
    """把线路人数变化推给该大厅内所有玩家（用于分线面板实时刷新）。

    参数:
        lobby: 大厅。
    """
    payload = {
        "id": lobby.id,
        "total": lobby.total,
        "lines": [lobby.lines[i].brief() for i in sorted(lobby.lines)],
    }
    targets = [s for line in lobby.lines.values() for s in line.sessions()]
    await hub.broadcast(targets, "lobby.lines", payload)


# ---------------------------------------------------------------- 包处理


@on_packet("lobby.list")
async def _handle_list(session: Session, packet: Packet) -> None:
    """列出全部大厅。

    参数:
        session: 会话。
        packet: 请求包。
    """
    await session.send(
        "lobby.list",
        {"lobbies": manager.list_brief(), "online": hub.online_count},
        packet.seq,
    )


@on_packet("lobby.join")
async def _handle_join(session: Session, packet: Packet) -> None:
    """进入大厅。

    参数:
        session: 会话。
        packet: 请求包。
    """
    lobby_id = packet.str_of("id", max_len=32)
    want = packet.int_of("line", 0)
    if (lobby := manager.get(lobby_id)) is None:
        raise ProtocolError(Code.NO_LOBBY, f"大厅 {lobby_id} 不存在")

    # 先定线再离场：目标线路不可用时保持原状态不变，避免玩家掉进「无大厅」
    target = _resolve_target(lobby, want)
    await _leave(session, notify_self=False)
    await _enter(session, lobby, target, packet.seq)


@on_packet("lobby.switch")
async def _handle_switch(session: Session, packet: Packet) -> None:
    """在同一大厅内换线。

    参数:
        session: 会话。
        packet: 请求包。
    """
    lobby, current = _require_line(session)
    want = packet.int_of("line", 0)
    if want == current.index:
        raise ProtocolError(Code.BAD_FIELD, "已经在这条线路上了")

    target = _resolve_target(lobby, want)
    if target is current:
        raise ProtocolError(Code.BAD_FIELD, "已经在这条线路上了")

    await _leave(session, notify_self=False)
    # 原线可能因为清空被回收，这里重新取一次目标线路对象
    await _enter(session, lobby, lobby.ensure_line(target.index), packet.seq)


@on_packet("lobby.leave")
async def _handle_leave(session: Session, packet: Packet) -> None:
    """离开大厅。

    参数:
        session: 会话。
        packet: 请求包。
    """
    await _leave(session, seq=packet.seq)


@on_packet("lobby.move")
async def _handle_move(session: Session, packet: Packet) -> None:
    """位置上报。服务端做边界钳制后写入快照，由 tick 统一广播。

    参数:
        session: 会话。
        packet: 请求包。
    """
    lobby, line = _require_line(session)
    avatar = _avatar_of(session, line)
    avatar.x = min(max(packet.float_of("x", avatar.x), 0.0), lobby.width)
    avatar.y = min(max(packet.float_of("y", avatar.y), 0.0), lobby.height)
    avatar.dir = min(max(packet.int_of("dir", avatar.dir), 0), 3)
    avatar.moving = packet.bool_of("moving", avatar.moving)
    avatar.stamp = int(time.time() * 1000)
    line.dirty = True


@on_packet("lobby.chat")
async def _handle_chat(session: Session, packet: Packet) -> None:
    """线路内聊天。

    参数:
        session: 会话。
        packet: 请求包。
    """
    _, line = _require_line(session)
    text = packet.str_of("text", max_len=CHAT_MAX_LEN)
    now = time.monotonic()
    if now - float(session.state.get(KEY_CHAT_AT, 0.0)) < CHAT_INTERVAL:
        raise ProtocolError(Code.RATE_LIMIT, "说得太快了，缓一缓")
    session.state[KEY_CHAT_AT] = now
    await hub.broadcast(
        line.sessions(),
        "lobby.chat",
        {
            "uid": session.uid,
            "name": session.nickname,
            "text": text,
            "ms": int(time.time() * 1000),
        },
    )


@on_session_disconnect
async def _on_disconnect(session: Session) -> None:
    """断线清理。

    参数:
        session: 会话。
    """
    await _leave(session, notify_self=False)


# ---------------------------------------------------------------- 同步循环


async def _tick_loop() -> None:
    """位置快照广播循环。"""
    while True:
        # 每轮重新计算，在线调整 tick 频率后立即生效
        await asyncio.sleep(1.0 / float(config.game_lobby_tick_rate))
        # 后台常驻任务：任何异常都不能让循环退出，否则全服位置同步会静默停摆
        try:
            await _tick_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("[mgga_server] 大厅同步循环异常", e=exc)


async def _tick_once() -> None:
    """广播一帧位置快照。"""
    jobs = []
    for lobby in manager.lobbies.values():
        for line in lobby.lines.values():
            if not line.dirty or not line.members:
                continue
            line.dirty = False
            jobs.append(
                hub.broadcast(
                    line.sessions(),
                    "lobby.state",
                    {"ps": [a.snapshot() for a in line.avatars.values()]},
                )
            )
    if jobs:
        await asyncio.gather(*jobs, return_exceptions=True)
