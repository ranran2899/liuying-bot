"""会话对象与会话表。

一个 Session 对应一条客户端 WebSocket 连接。业务插件通过
``session.state[...]`` 存放自己的私有数据（如所在线路、所在对局），
避免各插件之间互相 import 具体类型。
"""

from __future__ import annotations

import asyncio
import itertools
from typing import Any

from nonebot.log import logger

from .protocol import Packet

_ids = itertools.count(1)


class Session:
    """一条已建立的客户端连接。"""

    __slots__ = ("sid", "ws", "uid", "username", "nickname", "state", "alive", "_lock", "last_seen")

    def __init__(self, ws: Any) -> None:
        self.sid: int = next(_ids)
        self.ws = ws
        #: 登录后填充；未登录时为 0
        self.uid: int = 0
        self.username: str = ""
        self.nickname: str = "游客"
        #: 各插件的私有状态
        self.state: dict[str, Any] = {}
        self.alive: bool = True
        self.last_seen: float = 0.0
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ 属性
    @property
    def authed(self) -> bool:
        return self.uid > 0

    def brief(self) -> dict[str, Any]:
        """给其它玩家看的最小信息。"""
        return {"uid": self.uid, "name": self.nickname}

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Session #{self.sid} uid={self.uid} {self.nickname}>"

    # ------------------------------------------------------------------ 发包
    async def send(self, packet_type: str, data: dict[str, Any] | None = None,
                   seq: int | None = None) -> None:
        """发送一个包；连接已断开时静默忽略。"""
        if not self.alive:
            return
        payload = Packet(packet_type, data or {}, seq).encode()
        try:
            async with self._lock:
                await self.ws.send_text(payload)
        except Exception:  # noqa: BLE001 - 发送失败即视为断线
            self.alive = False
            logger.debug(f"[mgga_server] {self} 发送失败，标记断线")

    async def send_error(self, code: str, msg: str, on: str = "", seq: int | None = None) -> None:
        await self.send("error", {"code": code, "msg": msg, "on": on}, seq)

    async def close(self, reason: str = "") -> None:
        self.alive = False
        try:
            await self.ws.close(reason=reason[:120])
        except Exception:  # noqa: BLE001
            pass


class SessionHub:
    """全局在线会话表。"""

    def __init__(self) -> None:
        self._by_sid: dict[int, Session] = {}
        self._by_uid: dict[int, Session] = {}

    # ------------------------------------------------------------------ 增删
    def add(self, session: Session) -> None:
        self._by_sid[session.sid] = session

    def remove(self, session: Session) -> None:
        self._by_sid.pop(session.sid, None)
        if session.uid and self._by_uid.get(session.uid) is session:
            self._by_uid.pop(session.uid, None)

    def bind_uid(self, session: Session) -> Session | None:
        """登录成功后绑定 uid；返回被顶下线的旧会话（若有）。"""
        old = self._by_uid.get(session.uid)
        self._by_uid[session.uid] = session
        return old if old is not None and old is not session else None

    # ------------------------------------------------------------------ 查询
    def by_uid(self, uid: int) -> Session | None:
        return self._by_uid.get(uid)

    def all(self) -> list[Session]:
        return list(self._by_sid.values())

    @property
    def online_count(self) -> int:
        return len(self._by_uid)

    # ------------------------------------------------------------------ 广播
    async def broadcast(self, targets: list[Session], packet_type: str,
                        data: dict[str, Any]) -> None:
        payload = Packet(packet_type, data).encode()
        for session in targets:
            if not session.alive:
                continue
            try:
                async with session._lock:  # noqa: SLF001 - 同模块内的受控访问
                    await session.ws.send_text(payload)
            except Exception:  # noqa: BLE001
                session.alive = False


hub = SessionHub()
