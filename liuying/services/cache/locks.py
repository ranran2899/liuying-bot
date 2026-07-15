"""
异步锁工具

提供异步可重入锁实现，支持在异步环境中安全使用。
"""

import asyncio
from types import TracebackType
from typing import Self


class AsyncRLock:
    """异步可重入锁

    类似于 threading.RLock，但适用于异步环境。
    同一个协程可以多次获取锁，需要相同次数的释放。
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._owner: asyncio.Task | None = None
        self._count = 0

    async def acquire(self) -> bool:
        """获取锁

        返回:
            bool: 总是返回True
        """
        current_task = asyncio.current_task()
        if self._owner == current_task:
            self._count += 1
            return True
        await self._lock.acquire()
        self._owner = current_task
        self._count = 1
        return True

    async def release(self) -> None:
        """释放锁"""
        current_task = asyncio.current_task()
        if self._owner != current_task:
            raise RuntimeError("无法释放未持有的锁")
        self._count -= 1
        if self._count == 0:
            self._owner = None
            self._lock.release()

    def locked(self) -> bool:
        """检查锁是否被占用

        返回:
            bool: 是否被占用
        """
        return self._lock.locked()

    async def __aenter__(self) -> Self:
        await self.acquire()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.release()
