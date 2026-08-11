"""会话对象与会话表。

一个 Session 对应一条客户端 WebSocket 连接。业务插件通过
``session.state[...]`` 存放自己的私有数据（如所在线路、所在对局），
避免各插件之间互相 import 具体类型。
"""

import asyncio
import itertools
import time
from collections.abc import Iterable
from typing import Any

from liuying.utils.log import logger

from .protocol import Code, Packet

#: 会话自增号
_ids = itertools.count(1)

#: 广播分片大小，避免一次性创建过多协程
BROADCAST_CHUNK = 64


class RateLimiter:
    """令牌桶限流器，用于约束单连接的收包频率。"""

    __slots__ = ("_capacity", "_rate", "_stamp", "_tokens")

    def __init__(self, rate: int, burst: int | None = None) -> None:
        self._rate = float(rate)
        self._capacity = float(burst if burst is not None else rate * 2)
        self._tokens = self._capacity
        self._stamp = time.monotonic()

    def allow(self, cost: float = 1.0) -> bool:
        """尝试消耗令牌。

        参数:
            cost: 本次消耗量。

        返回:
            bool: 是否放行。
        """
        now = time.monotonic()
        self._tokens = min(
            self._capacity, self._tokens + (now - self._stamp) * self._rate
        )
        self._stamp = now
        if self._tokens < cost:
            return False
        self._tokens -= cost
        return True


class Session:
    """一条已建立的客户端连接。"""

    __slots__ = (
        "_lock",
        "alive",
        "last_seen",
        "limiter",
        "nickname",
        "sid",
        "state",
        "uid",
        "username",
        "ws",
    )

    def __init__(self, ws: Any, *, packet_rate: int = 60) -> None:
        self.sid: int = next(_ids)
        self.ws = ws
        #: 登录后填充；未登录时为 0
        self.uid: int = 0
        self.username: str = ""
        self.nickname: str = "游客"
        #: 各插件的私有状态
        self.state: dict[str, Any] = {}
        self.alive: bool = True
        self.last_seen: float = time.monotonic()
        self.limiter = RateLimiter(packet_rate)
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ 属性
    @property
    def authed(self) -> bool:
        """是否已登录。"""
        return self.uid > 0

    def brief(self) -> dict[str, Any]:
        """给其它玩家看的最小信息。

        返回:
            dict[str, Any]: 仅含 uid 与昵称。
        """
        return {"uid": self.uid, "name": self.nickname}

    def __repr__(self) -> str:
        return f"<Session #{self.sid} uid={self.uid} {self.nickname}>"

    # ------------------------------------------------------------------ 发包
    async def send_raw(self, payload: str) -> bool:
        """发送已序列化好的文本帧。

        广播时复用同一份序列化结果，避免每个目标重复 ``json.dumps``。

        参数:
            payload: 已编码的 JSON 文本。

        返回:
            bool: 是否发送成功。
        """
        if not self.alive:
            return False
        # 网络写入可能因对端断开而抛出各种底层异常，此处降级为标记断线
        try:
            async with self._lock:
                await self.ws.send_text(payload)
        except Exception:  # noqa: BLE001
            self.alive = False
            logger.debug(f"[mgga_server] {self} 发送失败，标记断线")
            return False
        return True

    async def send(
        self,
        packet_type: str,
        data: dict[str, Any] | None = None,
        seq: int | None = None,
    ) -> None:
        """发送一个包；连接已断开时静默忽略。

        参数:
            packet_type: 包类型。
            data: 数据体。
            seq: 请求序号，回包时原样带回。
        """
        if not self.alive:
            return
        await self.send_raw(Packet(packet_type, data or {}, seq).encode())

    async def send_error(
        self, code: Code, msg: str, on: str = "", seq: int | None = None
    ) -> None:
        """发送错误包。

        参数:
            code: 错误码。
            msg: 展示文本。
            on: 触发错误的原包类型。
            seq: 请求序号。
        """
        await self.send("error", {"code": str(code), "msg": msg, "on": on}, seq)

    async def close(self, reason: str = "") -> None:
        """关闭连接。

        参数:
            reason: 关闭原因，超长会被截断。
        """
        self.alive = False
        # 对端可能已经消失，关闭动作失败无需处理
        try:
            await self.ws.close(reason=reason[:120])
        except Exception:  # noqa: BLE001
            logger.debug(f"[mgga_server] {self} 关闭连接时对端已断开")


class SessionHub:
    """全局在线会话表。"""

    __slots__ = ("_by_sid", "_by_uid")

    def __init__(self) -> None:
        self._by_sid: dict[int, Session] = {}
        self._by_uid: dict[int, Session] = {}

    # ------------------------------------------------------------------ 增删
    def add(self, session: Session) -> None:
        """登记新连接。

        参数:
            session: 会话对象。
        """
        self._by_sid[session.sid] = session

    def remove(self, session: Session) -> None:
        """移除连接。

        参数:
            session: 会话对象。
        """
        self._by_sid.pop(session.sid, None)
        if session.uid and self._by_uid.get(session.uid) is session:
            self._by_uid.pop(session.uid, None)

    def bind_uid(self, session: Session) -> Session | None:
        """登录成功后绑定 uid。

        参数:
            session: 已登录的会话。

        返回:
            Session | None: 被顶下线的旧会话。
        """
        old = self._by_uid.get(session.uid)
        self._by_uid[session.uid] = session
        return old if old is not None and old is not session else None

    # ------------------------------------------------------------------ 查询
    def by_uid(self, uid: int) -> Session | None:
        """按玩家 ID 查会话。

        参数:
            uid: 玩家 ID。

        返回:
            Session | None: 在线会话。
        """
        return self._by_uid.get(uid)

    def all(self) -> list[Session]:
        """全部连接（含未登录）。

        返回:
            list[Session]: 会话列表快照。
        """
        return list(self._by_sid.values())

    @property
    def online_count(self) -> int:
        """已登录在线人数。"""
        return len(self._by_uid)

    @property
    def conn_count(self) -> int:
        """连接总数（含未登录）。"""
        return len(self._by_sid)

    # ------------------------------------------------------------------ 广播
    async def broadcast(
        self, targets: Iterable[Session], packet_type: str, data: dict[str, Any]
    ) -> None:
        """向多个会话并发广播同一个包。

        参数:
            targets: 目标会话。
            packet_type: 包类型。
            data: 数据体。
        """
        alive = [s for s in targets if s.alive]
        if not alive:
            return
        payload = Packet(packet_type, data).encode()
        for i in range(0, len(alive), BROADCAST_CHUNK):
            chunk = alive[i : i + BROADCAST_CHUNK]
            await asyncio.gather(
                *(s.send_raw(payload) for s in chunk), return_exceptions=True
            )


hub = SessionHub()
