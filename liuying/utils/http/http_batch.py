"""HTTP批量请求管理模块，支持并发执行、结果聚合和进度回调。"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from httpx import Response

from liuying.utils.log import logger

from .http_utils import AsyncHttpx

_LOG_TAG = "BatchRequest"


@dataclass(slots=True)
class BatchRequestItem:
    """批量请求条目，存储单次请求配置和结果。

    参数:
        method: HTTP方法。
        url: 请求URL。
        kwargs: 请求参数。
        result: 响应结果，执行后填充。
        error: 异常对象，失败时填充。
        index: 在批次中的序号。
    """

    method: str
    url: str
    kwargs: dict[str, Any] = field(default_factory=dict)
    result: Response | None = None
    error: Exception | None = None
    index: int = 0

    @property
    def is_success(self) -> bool:
        """是否成功。"""
        return self.error is None and self.result is not None


@dataclass(slots=True)
class BatchResult:
    """批量请求结果聚合。

    参数:
        items: 所有请求条目列表。
        total: 总请求数。
        success_count: 成功数。
        failure_count: 失败数。
    """

    items: list[BatchRequestItem]
    total: int = 0
    success_count: int = 0
    failure_count: int = 0

    @property
    def successful_items(self) -> list[BatchRequestItem]:
        """成功的请求条目。"""
        return [item for item in self.items if item.is_success]

    @property
    def failed_items(self) -> list[BatchRequestItem]:
        """失败的请求条目。"""
        return [item for item in self.items if not item.is_success]

    @property
    def responses(self) -> list[Response]:
        """所有成功的响应列表。"""
        return [
            item.result for item in self.items if item.result is not None
        ]

    @property
    def all_success(self) -> bool:
        """是否全部成功。"""
        return self.failure_count == 0


class BatchRequestManager:
    """批量请求管理器，支持并发执行和结果聚合。

    参数:
        concurrency: 并发数限制。
        stop_on_error: 首个失败后是否取消剩余请求。
    """

    def __init__(
        self,
        concurrency: int = 10,
        stop_on_error: bool = False,
    ):
        self.concurrency = max(1, concurrency)
        self.stop_on_error = stop_on_error
        self._items: list[BatchRequestItem] = []

    def add(
        self,
        method: str,
        url: str | list[str],
        **kwargs,
    ) -> "BatchRequestManager":
        """添加一个请求到批次。

        参数:
            method: HTTP方法。
            url: 请求URL，支持多URL回退。
            **kwargs: 请求参数。

        返回:
            BatchRequestManager: self，支持链式调用。
        """
        item = BatchRequestItem(
            method=method,
            url=url,
            kwargs=kwargs,
            index=len(self._items),
        )
        self._items.append(item)
        return self

    def add_get(self, url: str | list[str], **kwargs) -> "BatchRequestManager":
        """添加GET请求。"""
        return self.add("GET", url, **kwargs)

    def add_post(self, url: str | list[str], **kwargs) -> "BatchRequestManager":
        """添加POST请求。"""
        return self.add("POST", url, **kwargs)

    def add_head(self, url: str | list[str], **kwargs) -> "BatchRequestManager":
        """添加HEAD请求。"""
        return self.add("HEAD", url, **kwargs)

    async def _execute_single(
        self,
        item: BatchRequestItem,
        semaphore: asyncio.Semaphore,
        on_progress: Callable[[int, int, BatchRequestItem], Awaitable[None]]
        | None = None,
    ) -> BatchRequestItem:
        """执行单个请求。

        参数:
            item: 请求条目。
            semaphore: 并发信号量。
            on_progress: 进度回调(已完成数, 总数, 当前条目)。

        返回:
            BatchRequestItem: 完成的请求条目。
        """
        async with semaphore:
            try:
                match item.method.upper():
                    case "GET":
                        item.result = await AsyncHttpx.get(
                            item.url, **item.kwargs
                        )
                    case "POST":
                        item.result = await AsyncHttpx.post(
                            item.url, **item.kwargs
                        )
                    case "HEAD":
                        item.result = await AsyncHttpx.head(
                            item.url, **item.kwargs
                        )
                    case _:
                        item.result = await AsyncHttpx.get(
                            item.url, **item.kwargs
                        )
            except Exception as e:
                item.error = e
                logger.warning(
                    f"批次请求[{item.index}] {item.method} {item.url} 失败: {e}",
                    _LOG_TAG,
                )

            if on_progress:
                await on_progress(
                    item.index + 1, len(self._items), item
                )
            return item

    async def execute(
        self,
        on_progress: Callable[[int, int, BatchRequestItem], Awaitable[None]]
        | None = None,
    ) -> BatchResult:
        """执行所有批量请求。

        参数:
            on_progress: 进度回调(已完成数, 总数, 当前完成的条目)。

        返回:
            BatchResult: 批量请求结果聚合。
        """
        if not self._items:
            return BatchResult(items=[], total=0)

        semaphore = asyncio.Semaphore(self.concurrency)
        total = len(self._items)
        logger.info(
            f"开始执行 {total} 个批量请求 (并发: {self.concurrency})",
            _LOG_TAG,
        )

        if self.stop_on_error:
            return await self._execute_with_stop_on_error(
                semaphore, on_progress
            )
        return await self._execute_all(semaphore, on_progress)

    async def _execute_all(
        self,
        semaphore: asyncio.Semaphore,
        on_progress: Callable[[int, int, BatchRequestItem], Awaitable[None]]
        | None,
    ) -> BatchResult:
        """执行所有请求，不因单个失败而停止。"""
        tasks = [
            self._execute_single(item, semaphore, on_progress)
            for item in self._items
        ]
        completed_items = list(await asyncio.gather(*tasks))
        return self._build_result(completed_items)

    async def _execute_with_stop_on_error(
        self,
        semaphore: asyncio.Semaphore,
        on_progress: Callable[[int, int, BatchRequestItem], Awaitable[None]]
        | None,
    ) -> BatchResult:
        """执行请求，首个失败后取消剩余请求。"""
        task_map: dict[asyncio.Task[BatchRequestItem], BatchRequestItem] = {}
        try:
            async with asyncio.TaskGroup() as tg:
                for item in self._items:
                    task = tg.create_task(
                        self._execute_single(item, semaphore, on_progress)
                    )
                    task_map[task] = item
        except* Exception as eg:
            logger.warning(
                f"批量执行中捕获异常组: {len(eg.exceptions)} 个",
                _LOG_TAG,
            )

        completed_items = []
        for task, item in task_map.items():
            if task.done() and not task.cancelled():
                completed_items.append(task.result())
            else:
                item.error = asyncio.CancelledError("因stop_on_error取消")
                completed_items.append(item)

        return self._build_result(completed_items)

    def _build_result(
        self, completed_items: list[BatchRequestItem]
    ) -> BatchResult:
        """构建批量结果聚合。

        参数:
            completed_items: 已完成的请求条目列表。

        返回:
            BatchResult: 结果聚合。
        """
        completed_items.sort(key=lambda x: x.index)
        success_count = sum(1 for item in completed_items if item.is_success)
        failure_count = len(completed_items) - success_count

        result = BatchResult(
            items=completed_items,
            total=len(completed_items),
            success_count=success_count,
            failure_count=failure_count,
        )
        logger.info(
            f"批量请求完成: {success_count}/{result.total} 成功, "
            f"{failure_count} 失败",
            _LOG_TAG,
        )
        return result

    def clear(self) -> None:
        """清空所有待执行请求。"""
        self._items.clear()

    @property
    def size(self) -> int:
        """待执行请求数。"""
        return len(self._items)
