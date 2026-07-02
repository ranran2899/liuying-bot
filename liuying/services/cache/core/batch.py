"""
缓存批量操作

提供批量获取、设置、删除缓存数据的功能，带并发控制。
"""

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, TypeAlias

from ..config import KeyType, cache_config
from .operations import CacheOperations
from .registry import TypeRegistry

GetFunc: TypeAlias = Callable[[str, KeyType], Coroutine[Any, Any, Any]]
SetFunc: TypeAlias = Callable[
    [str, KeyType, Any, int | None], Coroutine[Any, Any, bool]
]
DeleteFunc: TypeAlias = Callable[[str, KeyType], Coroutine[Any, Any, bool]]


@dataclass(slots=True)
class BatchResult:
    """批量操作结果"""

    success: bool
    """整体是否成功"""
    total: int
    """总操作数"""
    succeeded: int
    """成功数"""
    failed: int
    """失败数"""
    results: dict[str, Any]
    """各键的结果"""
    errors: dict[str, str]
    """各键的错误信息"""


class BatchExecutor:
    """缓存批量操作执行器

    封装批量获取、设置、删除缓存数据的功能，带并发控制。
    持有注册器、单条操作执行器和信号量依赖。
    """

    def __init__(
        self,
        registry: TypeRegistry,
        cache_ops: CacheOperations,
        semaphore: asyncio.Semaphore | None = None,
    ) -> None:
        """初始化批量操作执行器

        参数:
            registry: 类型注册器
            cache_ops: 单条操作执行器
            semaphore: 并发控制信号量
        """
        self._registry = registry
        self._cache_ops = cache_ops
        self._semaphore = semaphore or asyncio.Semaphore(
            cache_config.batch_concurrency_limit
        )

    @staticmethod
    def make_disabled_result(total: int, reason: str) -> BatchResult:
        """创建缓存未启用或不可用的批量操作结果

        参数:
            total: 总操作数
            reason: 失败原因

        返回:
            BatchResult: 批量操作结果
        """
        return BatchResult(
            success=False,
            total=total,
            succeeded=0,
            failed=total,
            results={},
            errors={"all": reason},
        )

    def _get_semaphore(
        self, semaphore: asyncio.Semaphore | None
    ) -> asyncio.Semaphore:
        """获取批量操作信号量

        参数:
            semaphore: 外部传入的信号量，为None时使用默认信号量

        返回:
            asyncio.Semaphore: 信号量实例
        """
        return semaphore or self._semaphore

    def _aggregate_results(
        self,
        task_results: list[Any],
        failure_label: str,
    ) -> BatchResult:
        """聚合批量操作结果

        直接使用 task_result 中返回的 cache_key，避免重复构建。
        内部函数已捕获异常并返回 (cache_key, value, error) 元组，
        Exception 情况仅在 asyncio.gather 层面异常时出现。

        参数:
            task_results: asyncio.gather 返回的结果列表
            failure_label: 失败标签（如"设置失败"、"删除失败"）

        返回:
            BatchResult: 聚合后的批量操作结果
        """
        results: dict[str, Any] = {}
        errors: dict[str, str] = {}
        succeeded = 0
        failed = 0

        for i, task_result in enumerate(task_results):
            match task_result:
                case Exception():
                    errors[f"task_{i}"] = str(task_result)
                    failed += 1
                case (
                    str() as cache_key,
                    bool() as success,
                    str() | None as error,
                ):
                    if error or not success:
                        errors[cache_key] = error or failure_label
                        failed += 1
                    else:
                        results[cache_key] = success
                        succeeded += 1
                case (str() as cache_key, _, str() as error):
                    errors[cache_key] = error
                    failed += 1
                case (str() as cache_key, value, None):
                    results[cache_key] = value
                    succeeded += 1

        return BatchResult(
            success=failed == 0,
            total=succeeded + failed,
            succeeded=succeeded,
            failed=failed,
            results=results,
            errors=errors,
        )

    async def multi_get(
        self,
        cache_type: str,
        keys: list[KeyType],
        get_func: GetFunc,
        semaphore: asyncio.Semaphore | None = None,
    ) -> BatchResult:
        """批量获取缓存数据，带并发控制

        参数:
            cache_type: 缓存类型
            keys: 键列表
            get_func: 单条获取函数
            semaphore: 并发控制信号量

        返回:
            BatchResult: 批量操作结果
        """
        resolved_type = cache_type.upper()
        if not self._registry.is_valid(resolved_type):
            return self.make_disabled_result(len(keys), "缓存类型未注册")

        sem = self._get_semaphore(semaphore)

        async def _get_single(key: KeyType) -> tuple[str, Any, str | None]:
            async with sem:
                try:
                    cache_key = self._registry.build_key(resolved_type, key)
                    result = await get_func(resolved_type, key)
                    return cache_key, result, None
                except Exception as e:
                    cache_key = self._registry.build_key(resolved_type, key)
                    return cache_key, None, str(e)

        tasks = [_get_single(key) for key in keys]
        task_results = await asyncio.gather(*tasks, return_exceptions=True)
        return self._aggregate_results(task_results, "获取失败")

    async def multi_set(
        self,
        cache_type: str,
        items: dict[KeyType, Any],
        set_func: SetFunc,
        expire: int | None = None,
        semaphore: asyncio.Semaphore | None = None,
    ) -> BatchResult:
        """批量设置缓存数据，带并发控制

        参数:
            cache_type: 缓存类型
            items: 键值对字典
            set_func: 单条设置函数
            expire: 过期时间（秒）
            semaphore: 并发控制信号量

        返回:
            BatchResult: 批量操作结果
        """
        resolved_type = cache_type.upper()
        if not self._registry.is_valid(resolved_type):
            return self.make_disabled_result(len(items), "缓存类型未注册")

        sem = self._get_semaphore(semaphore)

        async def _set_single(key: KeyType, value: Any) -> tuple[str, bool, str | None]:
            async with sem:
                try:
                    cache_key = self._registry.build_key(resolved_type, key)
                    success = await set_func(resolved_type, key, value, expire)
                    return cache_key, success, None
                except Exception as e:
                    cache_key = self._registry.build_key(resolved_type, key)
                    return cache_key, False, str(e)

        tasks = [_set_single(key, value) for key, value in items.items()]
        task_results = await asyncio.gather(*tasks, return_exceptions=True)
        return self._aggregate_results(task_results, "设置失败")

    async def multi_delete(
        self,
        cache_type: str,
        keys: list[KeyType],
        delete_func: DeleteFunc,
        semaphore: asyncio.Semaphore | None = None,
    ) -> BatchResult:
        """批量删除缓存数据，带并发控制

        参数:
            cache_type: 缓存类型
            keys: 键列表
            delete_func: 单条删除函数
            semaphore: 并发控制信号量

        返回:
            BatchResult: 批量操作结果
        """
        resolved_type = cache_type.upper()
        if not self._registry.is_valid(resolved_type):
            return self.make_disabled_result(len(keys), "缓存类型未注册")

        sem = self._get_semaphore(semaphore)

        async def _delete_single(key: KeyType) -> tuple[str, bool, str | None]:
            async with sem:
                try:
                    cache_key = self._registry.build_key(resolved_type, key)
                    success = await delete_func(resolved_type, key)
                    return cache_key, success, None
                except Exception as e:
                    cache_key = self._registry.build_key(resolved_type, key)
                    return cache_key, False, str(e)

        tasks = [_delete_single(key) for key in keys]
        task_results = await asyncio.gather(*tasks, return_exceptions=True)
        return self._aggregate_results(task_results, "删除失败")
