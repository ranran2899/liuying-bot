"""大厅与分线的数据结构。

概念：

* **大厅（Lobby）**：一张可自由走动的社交地图，例如「宿舍楼前广场」。
* **线路（Line）**：同一张大厅地图的一个并行副本，容量 30 人。
  人满后由服务器自动开新线（1 线、2 线、3 线…），玩家可手动切线，
  也可用 ``line = 0`` 让服务器自动分配到最合适的一条线。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ..core import Session


@dataclass(slots=True)
class Avatar:
    """玩家在大厅里的形象与位置。"""

    uid: int
    name: str
    x: float = 0.0
    y: float = 0.0
    dir: int = 2
    moving: bool = False
    #: 供客户端做插值的服务器时间戳（毫秒）
    stamp: int = 0

    def snapshot(self) -> list[Any]:
        """位置快照，用紧凑数组减少每帧带宽。"""
        return [self.uid, round(self.x, 1), round(self.y, 1), self.dir, int(self.moving)]

    def full(self) -> dict[str, Any]:
        return {"uid": self.uid, "name": self.name, "x": self.x, "y": self.y,
                "dir": self.dir, "moving": self.moving}


@dataclass(slots=True)
class Line:
    """大厅的一条线路。"""

    lobby_id: str
    index: int
    capacity: int
    members: dict[int, Session] = field(default_factory=dict)
    avatars: dict[int, Avatar] = field(default_factory=dict)
    #: 上一帧广播出去的快照，用于做增量
    dirty: bool = True
    created_at: float = field(default_factory=time.monotonic)

    @property
    def count(self) -> int:
        return len(self.members)

    @property
    def full(self) -> bool:
        return self.count >= self.capacity

    def brief(self) -> dict[str, Any]:
        return {"line": self.index, "count": self.count, "cap": self.capacity}

    def sessions(self) -> list[Session]:
        return list(self.members.values())


@dataclass(slots=True)
class Lobby:
    """一张大厅地图，内含若干条线路。"""

    id: str
    name: str
    capacity: int
    #: 地图逻辑尺寸（像素），客户端据此限制走动范围
    width: float = 1600.0
    height: float = 900.0
    spawn: tuple[float, float] = (800.0, 640.0)
    lines: dict[int, Line] = field(default_factory=dict)

    # ------------------------------------------------------------------ 分线
    def line(self, index: int) -> Line | None:
        return self.lines.get(index)

    def ensure_line(self, index: int) -> Line:
        line = self.lines.get(index)
        if line is None:
            line = Line(self.id, index, self.capacity)
            self.lines[index] = line
        return line

    def pick_line(self) -> Line:
        """自动分线：优先塞进「人最多但还没满」的线，人满则开新线。"""
        best: Line | None = None
        for line in self.lines.values():
            if line.full:
                continue
            if best is None or line.count > best.count:
                best = line
        if best is not None:
            return best
        index = 1
        while index in self.lines:
            index += 1
        return self.ensure_line(index)

    def prune(self) -> None:
        """回收空闲的空线路，但至少保留 1 线。"""
        for index in [i for i, ln in self.lines.items() if ln.count == 0 and i != 1]:
            self.lines.pop(index, None)

    @property
    def total(self) -> int:
        return sum(line.count for line in self.lines.values())

    def brief(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "cap": self.capacity,
            "total": self.total,
            "w": self.width,
            "h": self.height,
            "spawn": [self.spawn[0], self.spawn[1]],
            "lines": [self.lines[i].brief() for i in sorted(self.lines)],
        }


class LobbyManager:
    """全部大厅的注册表。"""

    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self.lobbies: dict[str, Lobby] = {}

    def register(self, lobby_id: str, name: str, *, width: float = 1600.0,
                 height: float = 900.0, spawn: tuple[float, float] = (800.0, 640.0)) -> Lobby:
        lobby = Lobby(lobby_id, name, self.capacity, width, height, spawn)
        lobby.ensure_line(1)
        self.lobbies[lobby_id] = lobby
        return lobby

    def get(self, lobby_id: str) -> Lobby | None:
        return self.lobbies.get(lobby_id)

    def list_brief(self) -> list[dict[str, Any]]:
        return [lobby.brief() for lobby in self.lobbies.values()]
