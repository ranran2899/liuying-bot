"""
任务执行器

负责任务的实际执行，支持同步/异步函数与并发实例控制。
"""

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from liuying.utils.log import logger

from .constants import SCHEDULER_EXECUTOR_SHUTDOWN_WAIT

_LOG_COMMAND = "SchedulerExecutor"


@dataclass(slots=True)
class ExecutionResult:
    """任务执行结果"""

    success: bool
    """是否成功"""
    error: Exception | None = None
    """错误信息"""
    result: Any = None
    """返回结果"""


class TaskExecutor:
    """
    任务执行器

    负责：
    - 执行同步/异步任务函数
    - 并发实例控制（每个任务独立的信号量）
    - 执行结果记录
    """

    def __init__(self) -> None:
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._running_counts: dict[str, int] = {}
        self._shutting_down = False

    def _get_semaphore(self, task_id: str, max_instances: int) -> asyncio.Semaphore:
        """获取或创建任务信号量"""
        if task_id not in self._semaphores:
            self._semaphores[task_id] = asyncio.Semaphore(max_instances)
            self._running_counts[task_id] = 0
        return self._semaphores[task_id]

    def can_run(self, task_id: str, max_instances: int) -> bool:
        """检查是否可以运行"""
        return self._running_counts.get(task_id, 0) < max_instances

    async def execute(
        self,
        task_id: str,
        func: Callable[..., Coroutine[Any, Any, Any] | Any],
        max_instances: int = 1,
        args: tuple = (),
        kwargs: dict[str, Any] | None = None,
        on_complete: Callable[[ExecutionResult], None] | None = None,
    ) -> ExecutionResult:
        """
        执行任务

        参数:
            task_id: 任务ID
            func: 任务函数
            max_instances: 最大并发实例数
            args: 位置参数
            kwargs: 关键字参数
            on_complete: 完成回调

        返回:
            ExecutionResult: 执行结果
        """
        semaphore = self._get_semaphore(task_id, max_instances)

        async with semaphore:
            if self._shutting_down:
                return ExecutionResult(
                    success=False,
                    error=RuntimeError("执行器正在关闭"),
                )

            self._running_counts[task_id] = (
                self._running_counts.get(task_id, 0) + 1
            )
            try:
                result = await self._execute_once(task_id, func, args, kwargs or {})

                if on_complete:
                    try:
                        on_complete(result)
                    except Exception as e:
                        logger.error(
                            f"任务完成回调执行失败: {task_id}",
                            _LOG_COMMAND,
                            e=e,
                        )

                return result
            finally:
                self._running_counts[task_id] = (
                    self._running_counts.get(task_id, 1) - 1
                )

    async def _execute_once(
        self,
        task_id: str,
        func: Callable[..., Coroutine[Any, Any, Any] | Any],
        args: tuple,
        kwargs: dict[str, Any],
    ) -> ExecutionResult:
        """执行一次任务"""
        try:
            async def _run_task() -> Any:
                """运行任务函数"""
                result = func(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    result = await result
                return result

            return ExecutionResult(success=True, result=await _run_task())
        except Exception as e:
            logger.error(
                f"任务执行失败: {task_id}",
                _LOG_COMMAND,
                e=e,
            )
            return ExecutionResult(success=False, error=e)

    async def shutdown(
        self,
        timeout: float = SCHEDULER_EXECUTOR_SHUTDOWN_WAIT,
    ) -> None:
        """关闭执行器，等待所有运行中的任务完成"""
        # 设置关闭标志，阻止新任务执行
        self._shutting_down = True

        running_task_ids = [
            tid for tid, count in self._running_counts.items() if count > 0
        ]

        if running_task_ids:
            deadline = asyncio.get_running_loop().time() + timeout

            for task_id in running_task_ids:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break

                semaphore = self._semaphores.get(task_id)
                if semaphore:
                    try:
                        await asyncio.wait_for(
                            semaphore.acquire(), timeout=remaining
                        )
                        semaphore.release()
                    except TimeoutError:
                        pass

        logger.debug("任务执行器已关闭", _LOG_COMMAND)
