"""大厅与分线的数据结构。

概念：

* **大厅（Lobby）**：一张可自由走动的社交地图，例如「宿舍楼前广场」。
* **线路（Line）**：同一张大厅地图的一个并行副本，容量取自全局配置。
  人满后由服务器自动开新线（1 线、2 线、3 线…），玩家可手动切线，
  也可用 ``line = 0`` 让服务器自动分配到最合适的一条线。

容量与最大线路数都从 :data:`..core.config` 实时读取，因此机器人在线改配置
后立即生效，无需重启。
"""

import time
from dataclasses import dataclass, field
from typing import Any

from ..core import Session, config


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
        """位置快照，用紧凑数组减少每帧带宽。

        返回:
            list[Any]: ``[uid, x, y, dir, moving]``。
        """
        return [
            self.uid,
            round(self.x, 1),
            round(self.y, 1),
            self.dir,
            int(self.moving),
        ]

    def full(self) -> dict[str, Any]:
        """完整形象数据，用于新玩家进入时的首帧同步。

        返回:
            dict[str, Any]: 形象字段。
        """
        return {
            "uid": self.uid,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "dir": self.dir,
            "moving": self.moving,
        }


@dataclass(slots=True)
class Line:
    """大厅的一条线路。"""

    lobby_id: str
    index: int
    members: dict[int, Session] = field(default_factory=dict)
    avatars: dict[int, Avatar] = field(default_factory=dict)
    #: 自上次广播以来是否有人移动/进出，无变化的帧直接跳过广播
    dirty: bool = True
    created_at: float = field(default_factory=time.monotonic)

    @property
    def capacity(self) -> int:
        """线路容量，实时取自全局配置。"""
        return config.game_lobby_capacity

    @property
    def count(self) -> int:
        """当前人数。"""
        return len(self.members)

    @property
    def full(self) -> bool:
        """是否已满。"""
        return self.count >= self.capacity

    def brief(self) -> dict[str, Any]:
        """线路概要。

        返回:
            dict[str, Any]: 线路号、人数与容量。
        """
        return {"line": self.index, "count": self.count, "cap": self.capacity}

    def sessions(self) -> list[Session]:
        """成员会话快照。

        返回:
            list[Session]: 会话列表。
        """
        return list(self.members.values())


@dataclass(slots=True)
class Lobby:
    """一张大厅地图，内含若干条线路。"""

    id: str
    name: str
    #: 地图逻辑尺寸（像素），客户端据此限制走动范围
    width: float = 1600.0
    height: float = 900.0
    spawn: tuple[float, float] = (800.0, 640.0)
    lines: dict[int, Line] = field(default_factory=dict)

    @property
    def capacity(self) -> int:
        """单线容量，实时取自全局配置。"""
        return config.game_lobby_capacity

    @property
    def max_lines(self) -> int:
        """允许存在的最大线路数。"""
        return config.game_lobby_max_lines

    # ------------------------------------------------------------------ 分线
    def line(self, index: int) -> Line | None:
        """按线路号取线路。

        参数:
            index: 线路号。

        返回:
            Line | None: 线路对象。
        """
        return self.lines.get(index)

    def ensure_line(self, index: int) -> Line:
        """取线路，不存在则创建。

        参数:
            index: 线路号。

        返回:
            Line: 线路对象。
        """
        if (line := self.lines.get(index)) is None:
            line = self.lines[index] = Line(self.id, index)
        return line

    def can_open(self, index: int) -> bool:
        """判断线路号是否允许被创建。

        客户端可任意指定线路号，若不加约束会被刷出海量空线路，故限制在
        ``1..max_lines`` 之间。

        参数:
            index: 线路号。

        返回:
            bool: 是否允许。
        """
        return 1 <= index <= self.max_lines

    def pick_line(self) -> Line | None:
        """自动分线：优先塞进「人最多但还没满」的线，人满则开新线。

        返回:
            Line | None: 选中的线路；全部线路已满且无法再开新线时为 ``None``。
        """
        best: Line | None = None
        for line in self.lines.values():
            if not line.full and (best is None or line.count > best.count):
                best = line
        if best is not None:
            return best

        index = next(
            (i for i in range(1, self.max_lines + 1) if i not in self.lines), 0
        )
        return self.ensure_line(index) if index else None

    def prune(self) -> None:
        """回收空闲的空线路，但至少保留 1 线。"""
        for index in [i for i, ln in self.lines.items() if ln.count == 0 and i != 1]:
            del self.lines[index]

    @property
    def total(self) -> int:
        """全部线路的总人数。"""
        return sum(line.count for line in self.lines.values())

    def brief(self) -> dict[str, Any]:
        """大厅概要。

        返回:
            dict[str, Any]: 地图信息与各线路人数。
        """
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

    __slots__ = ("lobbies",)

    def __init__(self) -> None:
        self.lobbies: dict[str, Lobby] = {}

    def register(
        self,
        lobby_id: str,
        name: str,
        *,
        width: float = 1600.0,
        height: float = 900.0,
        spawn: tuple[float, float] = (800.0, 640.0),
    ) -> Lobby:
        """注册一张大厅地图；同 id 重复注册时返回已有对象。

        参数:
            lobby_id: 地图 id。
            name: 展示名。
            width: 地图宽度。
            height: 地图高度。
            spawn: 出生点坐标。

        返回:
            Lobby: 大厅对象。
        """
        if (exist := self.lobbies.get(lobby_id)) is not None:
            return exist
        lobby = Lobby(lobby_id, name, width, height, spawn)
        lobby.ensure_line(1)
        self.lobbies[lobby_id] = lobby
        return lobby

    def get(self, lobby_id: str) -> Lobby | None:
        """按 id 取大厅。

        参数:
            lobby_id: 地图 id。

        返回:
            Lobby | None: 大厅对象。
        """
        return self.lobbies.get(lobby_id)

    def list_brief(self) -> list[dict[str, Any]]:
        """全部大厅概要。

        返回:
            list[dict[str, Any]]: 概要列表。
        """
        return [lobby.brief() for lobby in self.lobbies.values()]
