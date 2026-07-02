"""
任务执行器
负责任务的实际执行，支持异步、并发控制、失败重试
"""

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from liuying.utils.log import logger


@dataclass(slots=True)
class ExecutionResult:
    """任务执行结果"""

    success: bool
    """是否成功"""
    error: Exception | None = None
    """错误信息"""
    result: Any = None
    """返回结果"""
    start_time: datetime = field(default_factory=datetime.now)
    """开始时间"""
    end_time: datetime | None = None
    """结束时间"""

    @property
    def duration(self) -> float | None:
        """执行耗时（秒）"""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None


@dataclass(slots=True)
class RetryPolicy:
    """重试策略"""

    max_retries: int = 3
    """最大重试次数"""
    retry_delay: float = 1.0
    """重试延迟（秒）"""
    exponential_backoff: bool = True
    """是否指数退避"""
    retry_exceptions: tuple[type[Exception], ...] | None = None
    """需要重试的异常类型，None 表示所有异常"""

    def should_retry(self, exception: Exception, attempt: int) -> bool:
        """判断是否应该重试"""
        if attempt >= self.max_retries:
            return False

        if self.retry_exceptions is None:
            return True

        return isinstance(exception, self.retry_exceptions)

    def get_delay(self, attempt: int) -> float:
        """获取重试延迟"""
        if self.exponential_backoff:
            return self.retry_delay * (2**attempt)
        return self.retry_delay


class TaskExecutor:
    """
    任务执行器

    负责：
    - 执行同步/异步任务函数
    - 并发实例控制（每个任务独立的信号量）
    - 失败重试机制
    - 执行结果记录
    """

    def __init__(self, retry_policy: RetryPolicy | None = None) -> None:
        self._retry_policy = retry_policy or RetryPolicy(max_retries=0)
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._running_counts: dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._shutting_down = False

    def _get_semaphore(self, task_id: str, max_instances: int) -> asyncio.Semaphore:
        """获取或创建任务信号量"""
        if task_id not in self._semaphores:
            self._semaphores[task_id] = asyncio.Semaphore(max_instances)
            self._running_counts[task_id] = 0
        return self._semaphores[task_id]

    def get_running_count(self, task_id: str) -> int:
        """获取正在运行的实例数"""
        return self._running_counts.get(task_id, 0)

    def can_run(self, task_id: str, max_instances: int) -> bool:
        """检查是否可以运行"""
        return self.get_running_count(task_id) < max_instances

    async def execute(
        self,
        task_id: str,
        func: Callable[..., Coroutine[Any, Any, Any] | Any],
        max_instances: int = 1,
        args: tuple = (),
        kwargs: dict[str, Any] | None = None,
        on_complete: Callable[[ExecutionResult], None] | None = None,
        timeout: float | None = None,
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
            timeout: 超时时间（秒），None 表示不限制

        返回:
            ExecutionResult: 执行结果
        """
        kwargs = kwargs or {}
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
                result = await self._execute_with_retry(
                    task_id, func, args, kwargs, timeout
                )

                if on_complete:
                    try:
                        on_complete(result)
                    except Exception as e:
                        logger.error(f"任务完成回调执行失败: {task_id}", e=e)

                return result
            finally:
                count = self._running_counts.get(task_id, 1)
                self._running_counts[task_id] = count - 1

    async def _execute_with_retry(
        self,
        task_id: str,
        func: Callable[..., Coroutine[Any, Any, Any] | Any],
        args: tuple,
        kwargs: dict[str, Any],
        timeout: float | None = None,
    ) -> ExecutionResult:
        """带重试的任务执行"""
        attempt = 0
        last_error: Exception | None = None
        result = ExecutionResult(success=False, start_time=datetime.now())

        while True:
            result = await self._execute_once(task_id, func, args, kwargs, timeout)

            if result.success:
                return result

            last_error = result.error

            if last_error and self._retry_policy.should_retry(last_error, attempt):
                attempt += 1
                delay = self._retry_policy.get_delay(attempt - 1)
                logger.warning(
                    f"任务执行失败，{delay:.1f}秒后重试 (第{attempt}次): {task_id}",
                    e=last_error,
                )
                await asyncio.sleep(delay)
            else:
                break

        return ExecutionResult(
            success=False,
            error=last_error,
            start_time=result.start_time,
            end_time=datetime.now(),
        )

    async def _execute_once(
        self,
        task_id: str,
        func: Callable[..., Coroutine[Any, Any, Any] | Any],
        args: tuple,
        kwargs: dict[str, Any],
        timeout: float | None = None,
    ) -> ExecutionResult:
        """执行一次任务（支持超时控制）"""
        start_time = datetime.now()

        try:
            async def _run_task() -> Any:
                """运行任务函数"""
                result = func(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    result = await result
                return result

            match timeout:
                case timeout if timeout is not None and timeout > 0:
                    task_result = await asyncio.wait_for(_run_task(), timeout=timeout)
                case _:
                    task_result = await _run_task()

            return ExecutionResult(
                success=True,
                result=task_result,
                start_time=start_time,
                end_time=datetime.now(),
            )

        except TimeoutError:
            logger.warning(f"任务执行超时 ({timeout}秒): {task_id}")
            return ExecutionResult(
                success=False,
                error=TimeoutError(f"任务执行超时: {timeout}秒"),
                start_time=start_time,
                end_time=datetime.now(),
            )
        except Exception as e:
            logger.error(f"任务执行失败: {task_id}", e=e)
            return ExecutionResult(
                success=False,
                error=e,
                start_time=start_time,
                end_time=datetime.now(),
            )

    async def shutdown(self, timeout: float = 30.0) -> None:
        """关闭执行器，等待所有运行中的任务完成"""
        # 设置关闭标志，阻止新任务执行
        self._shutting_down = True

        running_task_ids = [
            tid for tid, count in self._running_counts.items() if count > 0
        ]

        if running_task_ids:
            logger.debug(f"等待 {len(running_task_ids)} 个运行中的任务完成...")
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

        logger.debug("任务执行器已关闭")
