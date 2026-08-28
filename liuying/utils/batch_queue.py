"""通用异步批量写入队列"""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress

from liuying.utils.log import logger


class BatchQueue[T]:
    """异步批量写入队列

    按时间间隔或批量大小将记录批量刷写到数据库，
    供聊天记录、调用统计等钩子复用。
    """

    def __init__(self, name: str, write: Callable[[list[T]], Awaitable[None]]):
        """初始化队列

        参数:
            name: 队列名称，用于日志
            write: 批量写入协程函数，接收记录列表
        """
        self._name = name
        self._write = write
        self._queue: asyncio.Queue[T] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._running = False
        self._interval = 60
        self._size = 100

    def add(self, record: T) -> None:
        """添加记录到队列

        参数:
            record: 记录数据
        """
        self._queue.put_nowait(record)

    async def start(self, interval: int, size: int) -> None:
        """启动队列处理任务

        参数:
            interval: 批量写入间隔（秒）
            size: 单批最大数量
        """
        if self._running:
            return
        self._running = True
        self._interval = interval
        self._size = size
        self._task = asyncio.create_task(self._process())
        logger.info(f"{self._name}队列已启动", command="BatchQueue")

    async def stop(self) -> None:
        """停止队列处理任务并刷写剩余记录"""
        self._running = False
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self._flush_remaining()
        logger.info(f"{self._name}队列已停止", command="BatchQueue")

    async def _flush_remaining(self) -> None:
        """刷写队列中剩余的记录"""
        records = []
        while not self._queue.empty():
            records.append(self._queue.get_nowait())
        if records:
            await self._write(records)

    async def _process(self) -> None:
        """循环处理队列，按间隔批量刷写"""
        while self._running:
            records: list[T] = []
            try:
                await asyncio.sleep(self._interval)
                while not self._queue.empty() and len(records) < self._size:
                    records.append(self._queue.get_nowait())

                if records:
                    await self._write(records)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"处理{self._name}队列失败", command="BatchQueue", e=e)
