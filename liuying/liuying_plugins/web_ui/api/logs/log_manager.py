import asyncio
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

_T = TypeVar("_T")
LogListener = Callable[[_T], Awaitable[None]]


class LogStorage(Generic[_T]):
    """
    日志存储
    """

    def __init__(self, rotation: float = 5 * 60):
        self.count, self.rotation = 0, rotation
        self.logs: dict[int, str] = {}
        self.listeners: set[LogListener[str]] = set()
        # 后台广播任务引用，防止被 GC 回收
        self._broadcast_tasks: set[asyncio.Task] = set()

    async def add(self, log: str):
        seq = self.count = self.count + 1
        self.logs[seq] = log
        asyncio.get_running_loop().call_later(self.rotation, self.remove, seq)
        # 解耦广播：每个监听器独立任务，避免慢客户端阻塞日志写入
        for listener in self.listeners:
            task = asyncio.create_task(self._safe_notify(listener, log))
            self._broadcast_tasks.add(task)
            task.add_done_callback(self._broadcast_tasks.discard)
        return seq

    @staticmethod
    async def _safe_notify(listener: LogListener[str], log: str) -> None:
        """安全调用监听器，吞掉异常避免影响其他监听器"""
        try:
            await listener(log)
        except Exception:
            pass

    def remove(self, seq: int):
        self.logs.pop(seq, None)


LOG_STORAGE: LogStorage[str] = LogStorage[str]()
