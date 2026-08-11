"""match —— 对局房间模块（由大厅发起的组队开局）。

大厅是社交场，真正的一局逃生游戏在「对局房间」里进行。房间由服务器创建并分配
唯一 ID，队长点击开始后，服务器生成关卡随机种子并下发给全体成员，保证各端地图一致。

协议：

* ``match.create`` {}            -> ``match.state``
* ``match.list``   {}            -> ``match.list`` {matches:[...]}
* ``match.join``   {id}          -> ``match.state``
* ``match.leave``  {}            -> ``match.left``
* ``match.ready``  {ready}       -> 广播 ``match.state``
* ``match.start``  {}            -> 广播 ``match.started`` {seed, members}
* ``match.result`` {escaped, time} -> 写入账号战绩，回 ``auth.profile``

服务端主动推送：``match.state``（成员/准备状态变化）、``match.started``。
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any

from nonebot.log import logger

from .. import auth as _auth
from ..auth import account_of
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

__all__ = ["Match", "matches"]

_next_id = 1000


@dataclass(slots=True)
class Match:
    """一局游戏的房间。"""

    id: int
    leader_uid: int
    lobby_id: str
    capacity: int
    members: dict[int, Session] = field(default_factory=dict)
    ready: set[int] = field(default_factory=set)
    started: bool = False
    seed: int = 0
    created_at: float = field(default_factory=time.monotonic)

    @property
    def count(self) -> int:
        return len(self.members)

    @property
    def full(self) -> bool:
        return self.count >= self.capacity

    def sessions(self) -> list[Session]:
        return list(self.members.values())

    def brief(self) -> dict[str, Any]:
        leader = self.members.get(self.leader_uid)
        return {
            "id": self.id,
            "leader": leader.nickname if leader else "—",
            "count": self.count,
            "cap": self.capacity,
            "started": self.started,
            "lobby": self.lobby_id,
        }

    def state(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "leader_uid": self.leader_uid,
            "cap": self.capacity,
            "started": self.started,
            "members": [
                {"uid": s.uid, "name": s.nickname, "ready": s.uid in self.ready,
                 "leader": s.uid == self.leader_uid}
                for s in self.members.values()
            ],
        }


matches: dict[int, Match] = {}


def match_of(session: Session) -> Match | None:
    value = session.state.get("match")
    return value if isinstance(value, Match) else None


def _require_match(session: Session) -> Match:
    match = match_of(session)
    if match is None:
        raise ProtocolError(Code.NO_MATCH, "你不在任何对局房间中")
    return match


async def _push_state(match: Match) -> None:
    await hub.broadcast(match.sessions(), "match.state", match.state())


async def _remove(session: Session) -> None:
    match = match_of(session)
    if match is None:
        return
    match.members.pop(session.uid, None)
    match.ready.discard(session.uid)
    session.state.pop("match", None)
    if match.count == 0:
        matches.pop(match.id, None)
        return
    if match.leader_uid == session.uid:
        match.leader_uid = next(iter(match.members))
    await _push_state(match)


# ---------------------------------------------------------------- 包处理

@on_packet("match.create")
async def _handle_create(session: Session, packet: Packet) -> None:
    global _next_id
    await _remove(session)
    _next_id += 1
    match = Match(id=_next_id, leader_uid=session.uid,
                  lobby_id=str(session.state.get("lobby_id", "")),
                  capacity=config.game_match_capacity)
    match.members[session.uid] = session
    matches[match.id] = match
    session.state["match"] = match
    await session.send("match.state", match.state(), packet.seq)
    logger.info(f"[mgga_server] {session.nickname} 创建对局 #{match.id}")


@on_packet("match.list")
async def _handle_list(session: Session, packet: Packet) -> None:
    lobby_id = str(session.state.get("lobby_id", ""))
    visible = [m.brief() for m in matches.values()
               if not m.started and (not lobby_id or m.lobby_id == lobby_id)]
    await session.send("match.list", {"matches": visible}, packet.seq)


@on_packet("match.join")
async def _handle_join(session: Session, packet: Packet) -> None:
    match_id = packet.int_of("id")
    match = matches.get(match_id)
    if match is None or match.started:
        raise ProtocolError(Code.NO_MATCH, "该对局不存在或已开始")
    if match.full:
        raise ProtocolError(Code.MATCH_FULL, f"队伍已满（{match.capacity} 人）")
    await _remove(session)
    match.members[session.uid] = session
    session.state["match"] = match
    await session.send("match.state", match.state(), packet.seq)
    await _push_state(match)


@on_packet("match.leave")
async def _handle_leave(session: Session, packet: Packet) -> None:
    await _remove(session)
    await session.send("match.left", {}, packet.seq)


@on_packet("match.ready")
async def _handle_ready(session: Session, packet: Packet) -> None:
    match = _require_match(session)
    if bool(packet.data.get("ready", True)):
        match.ready.add(session.uid)
    else:
        match.ready.discard(session.uid)
    await _push_state(match)


@on_packet("match.start")
async def _handle_start(session: Session, packet: Packet) -> None:
    match = _require_match(session)
    if match.leader_uid != session.uid:
        raise ProtocolError(Code.NOT_LEADER, "只有队长可以开始游戏")
    waiting = [s.nickname for s in match.sessions()
               if s.uid != match.leader_uid and s.uid not in match.ready]
    if waiting:
        raise ProtocolError(Code.BAD_FIELD, "还有队友未准备：" + "、".join(waiting))

    match.started = True
    match.seed = random.randint(1, 2_147_483_646)
    payload = {"seed": match.seed, "id": match.id,
               "members": [{"uid": s.uid, "name": s.nickname} for s in match.sessions()]}
    await hub.broadcast(match.sessions(), "match.started", payload)
    logger.info(f"[mgga_server] 对局 #{match.id} 开始，seed={match.seed}，{match.count} 人")


@on_packet("match.result")
async def _handle_result(session: Session, packet: Packet) -> None:
    """客户端上报本局结果，服务端写入账号战绩（权威数据以服务端为准）。"""
    escaped = bool(packet.data.get("escaped", False))
    survive = max(0.0, packet.float_of("time", 0.0))
    account = account_of(session)
    await _auth.store.record_result(account.uid, escaped, survive)
    if escaped:
        account.escapes += 1
        if account.best_time < 0 or survive < account.best_time:
            account.best_time = survive
    else:
        account.deaths += 1

    match = match_of(session)
    if match is not None and match.started:
        await _remove(session)
    await session.send("auth.profile", {"profile": account.profile()}, packet.seq)


@on_session_disconnect
async def _on_disconnect(session: Session) -> None:
    await _remove(session)
