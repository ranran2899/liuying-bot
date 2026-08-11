"""match —— 对局房间模块（由大厅发起的组队开局）。

大厅是社交场，真正的一局逃生游戏在「对局房间」里进行。房间由服务器创建并分配
唯一 ID，队长点击开始后，服务器生成关卡随机种子并下发给全体成员，保证各端地图一致。

协议：

* ``match.create`` {}              -> ``match.state``
* ``match.list``   {}              -> ``match.list`` {matches:[...]}
* ``match.join``   {id}            -> ``match.state``
* ``match.leave``  {}              -> ``match.left``
* ``match.ready``  {ready}         -> 广播 ``match.state``
* ``match.start``  {}              -> 广播 ``match.started`` {seed, members}
* ``match.result`` {escaped}       -> 写入账号战绩，回 ``auth.profile``

服务端主动推送：``match.state``（成员/准备状态变化）、``match.started``。

结算时长以**服务端计时**为准，客户端上报的时间只作参考，避免改包刷榜。
"""

import asyncio
import itertools
import random
import time
from dataclasses import dataclass, field
from typing import Any

from liuying.utils.log import logger
from liuying.utils.manager import PriorityLifecycle

from ..auth import uid_of
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
from ..models import GameAccount

__all__ = ["Match", "match_of", "matches"]

#: 房间号自增序列
_ids = itertools.count(1001)
#: 会话状态键
KEY_MATCH = "match"
KEY_LOBBY = "lobby_id"
#: 僵尸房间巡检间隔（秒）
GC_INTERVAL = 60.0


@dataclass(slots=True)
class Match:
    """一局游戏的房间。"""

    id: int
    leader_uid: int
    lobby_id: str
    members: dict[int, Session] = field(default_factory=dict)
    ready: set[int] = field(default_factory=set)
    started: bool = False
    seed: int = 0
    created_at: float = field(default_factory=time.monotonic)
    #: 开局时刻，用于服务端权威计时；未开局为 0
    started_at: float = 0.0

    @property
    def capacity(self) -> int:
        """房间容量，实时取自全局配置。"""
        return config.game_match_capacity

    @property
    def count(self) -> int:
        """当前人数。"""
        return len(self.members)

    @property
    def full(self) -> bool:
        """是否已满。"""
        return self.count >= self.capacity

    def sessions(self) -> list[Session]:
        """成员会话快照。

        返回:
            list[Session]: 会话列表。
        """
        return list(self.members.values())

    def elapsed(self) -> float:
        """已进行时长（秒）；未开局返回 ``0``。

        返回:
            float: 时长。
        """
        return time.monotonic() - self.started_at if self.started_at else 0.0

    def brief(self) -> dict[str, Any]:
        """房间概要，用于房间列表。

        返回:
            dict[str, Any]: 概要字段。
        """
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
        """房间完整状态。

        返回:
            dict[str, Any]: 状态字段。
        """
        return {
            "id": self.id,
            "leader_uid": self.leader_uid,
            "cap": self.capacity,
            "started": self.started,
            "members": [
                {
                    "uid": s.uid,
                    "name": s.nickname,
                    "ready": s.uid in self.ready,
                    "leader": s.uid == self.leader_uid,
                }
                for s in self.members.values()
            ],
        }


matches: dict[int, Match] = {}

_gc_task: asyncio.Task[None] | None = None


def match_of(session: Session) -> Match | None:
    """取会话所在房间。

    参数:
        session: 会话。

    返回:
        Match | None: 房间对象。
    """
    value = session.state.get(KEY_MATCH)
    return value if isinstance(value, Match) else None


def _require_match(session: Session) -> Match:
    """取会话所在房间；不在房间时抛错。

    参数:
        session: 会话。

    返回:
        Match: 房间对象。

    抛出:
        ProtocolError: 不在任何房间中。
    """
    if (match := match_of(session)) is None:
        raise ProtocolError(Code.NO_MATCH, "你不在任何对局房间中")
    return match


async def _push_state(match: Match) -> None:
    """向房间全员广播最新状态。

    参数:
        match: 房间。
    """
    await hub.broadcast(match.sessions(), "match.state", match.state())


async def _remove(session: Session) -> None:
    """把会话从其所在房间移除，必要时转移队长或解散房间。

    参数:
        session: 会话。
    """
    if (match := match_of(session)) is None:
        return
    match.members.pop(session.uid, None)
    match.ready.discard(session.uid)
    session.state.pop(KEY_MATCH, None)

    if not match.members:
        matches.pop(match.id, None)
        logger.debug(f"[mgga_server] 对局 #{match.id} 已解散")
        return
    if match.leader_uid == session.uid:
        match.leader_uid = next(iter(match.members))
    await _push_state(match)


# ---------------------------------------------------------------- 包处理


@on_packet("match.create")
async def _handle_create(session: Session, packet: Packet) -> None:
    """创建房间。

    参数:
        session: 会话。
        packet: 请求包。
    """
    await _remove(session)
    match = Match(
        id=next(_ids),
        leader_uid=session.uid,
        lobby_id=str(session.state.get(KEY_LOBBY, "")),
    )
    match.members[session.uid] = session
    matches[match.id] = match
    session.state[KEY_MATCH] = match
    await session.send("match.state", match.state(), packet.seq)
    logger.debug(f"[mgga_server] {session.nickname} 创建对局 #{match.id}")


@on_packet("match.list")
async def _handle_list(session: Session, packet: Packet) -> None:
    """列出可加入的房间（同大厅优先）。

    参数:
        session: 会话。
        packet: 请求包。
    """
    lobby_id = str(session.state.get(KEY_LOBBY, ""))
    visible = [
        m.brief()
        for m in matches.values()
        if not m.started and (not lobby_id or m.lobby_id == lobby_id)
    ]
    await session.send("match.list", {"matches": visible}, packet.seq)


@on_packet("match.join")
async def _handle_join(session: Session, packet: Packet) -> None:
    """加入房间。

    参数:
        session: 会话。
        packet: 请求包。
    """
    match = matches.get(packet.int_of("id"))
    if match is None or match.started:
        raise ProtocolError(Code.NO_MATCH, "该对局不存在或已开始")
    if match.full:
        raise ProtocolError(Code.MATCH_FULL, f"队伍已满（{match.capacity} 人）")

    await _remove(session)
    match.members[session.uid] = session
    session.state[KEY_MATCH] = match
    await session.send("match.state", match.state(), packet.seq)
    await _push_state(match)


@on_packet("match.leave")
async def _handle_leave(session: Session, packet: Packet) -> None:
    """离开房间。

    参数:
        session: 会话。
        packet: 请求包。
    """
    await _remove(session)
    await session.send("match.left", {}, packet.seq)


@on_packet("match.ready")
async def _handle_ready(session: Session, packet: Packet) -> None:
    """切换准备状态。

    参数:
        session: 会话。
        packet: 请求包。
    """
    match = _require_match(session)
    if match.started:
        raise ProtocolError(Code.BAD_FIELD, "对局已经开始了")
    if packet.bool_of("ready", True):
        match.ready.add(session.uid)
    else:
        match.ready.discard(session.uid)
    await _push_state(match)


@on_packet("match.start")
async def _handle_start(session: Session, packet: Packet) -> None:
    """队长开局，下发关卡种子。

    参数:
        session: 会话。
        packet: 请求包。
    """
    match = _require_match(session)
    if match.leader_uid != session.uid:
        raise ProtocolError(Code.NOT_LEADER, "只有队长可以开始游戏")
    if match.started:
        raise ProtocolError(Code.BAD_FIELD, "对局已经开始了")

    waiting = [
        s.nickname
        for s in match.sessions()
        if s.uid != match.leader_uid and s.uid not in match.ready
    ]
    if waiting:
        raise ProtocolError(Code.BAD_FIELD, "还有队友未准备：" + "、".join(waiting))

    match.started = True
    match.started_at = time.monotonic()
    match.seed = random.randint(1, 2_147_483_646)
    await hub.broadcast(
        match.sessions(),
        "match.started",
        {
            "seed": match.seed,
            "id": match.id,
            "members": [{"uid": s.uid, "name": s.nickname} for s in match.sessions()],
        },
    )
    logger.info(
        f"[mgga_server] 对局 #{match.id} 开始，seed={match.seed}，{match.count} 人"
    )


@on_packet("match.result")
async def _handle_result(session: Session, packet: Packet) -> None:
    """结算本局。

    只有处于「已开局房间」中的成员才能结算，且时长以服务端计时为准；
    结算后立即退出房间，因此重复上报会被 ``NO_MATCH`` 拒绝。

    参数:
        session: 会话。
        packet: 请求包。
    """
    uid = uid_of(session)
    match = _require_match(session)
    if not match.started:
        raise ProtocolError(Code.NO_MATCH, "对局尚未开始，无法结算")

    escaped = packet.bool_of("escaped", False)
    survive = min(max(match.elapsed(), 0.0), config.game_match_max_seconds)
    seed = match.seed

    await _remove(session)
    account = await GameAccount.record_result(uid, escaped, survive, seed)
    if account is None:
        raise ProtocolError(Code.NOT_AUTHED, "账号不存在，请重新登录")

    await session.send(
        "auth.profile",
        {"profile": account.profile(), "last": {"escaped": escaped, "time": survive}},
        packet.seq,
    )


@on_session_disconnect
async def _on_disconnect(session: Session) -> None:
    """断线清理。

    参数:
        session: 会话。
    """
    await _remove(session)


# ---------------------------------------------------------------- 僵尸房回收


@PriorityLifecycle.on_startup(priority=21)
async def _startup() -> None:
    """启动僵尸房间巡检。"""
    global _gc_task
    _gc_task = asyncio.create_task(_gc_loop())


@PriorityLifecycle.on_shutdown(priority=21)
async def _shutdown() -> None:
    """停止僵尸房间巡检。"""
    global _gc_task
    if _gc_task is not None:
        _gc_task.cancel()
        _gc_task = None


async def _gc_loop() -> None:
    """回收超时未结算或成员已全部掉线的房间。"""
    while True:
        await asyncio.sleep(GC_INTERVAL)
        # 后台常驻任务：异常不能中断循环，否则房间字典会持续膨胀
        try:
            _gc_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("[mgga_server] 对局回收异常", e=exc)


def _gc_once() -> None:
    """执行一次房间回收。"""
    limit = config.game_match_max_seconds
    for match in list(matches.values()):
        # 掉线成员由断线钩子清理，这里兜底处理钩子未覆盖到的残留引用
        for uid, member in list(match.members.items()):
            if not member.alive:
                match.members.pop(uid, None)
                match.ready.discard(uid)

        expired = match.started and match.elapsed() > limit
        if not match.members or expired:
            matches.pop(match.id, None)
            for member in match.sessions():
                member.state.pop(KEY_MATCH, None)
            logger.debug(f"[mgga_server] 回收僵尸对局 #{match.id}")
