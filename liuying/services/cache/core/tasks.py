"""
缓存后台定时任务

提供过期数据清理、降级检测、键记录清理和分布式锁初始化的后台任务。
"""

import asyncio
from collections.abc import Awaitable, Callable

from liuying.utils.log import logger

from ..config import LOG_COMMAND, CacheMode, cache_config
from ..containers.dict import CacheDict
from ..containers.list import CacheList
from .backend import BackendManager
from .degrade import DegradeManager
from .lock import LockManager
from .registry import TypeRegistry


class BackgroundTaskManager:
    """后台任务管理器

    管理过期数据清理、降级检测、键记录清理和分布式锁初始化的后台任务。
    持有缓存字典、缓存列表、锁、降级、后端、注册器依赖。
    """

    def __init__(
        self,
        dict_caches: dict[str, CacheDict],
        lock_mgr: LockManager,
        degrade_mgr: DegradeManager,
        backend_mgr: BackendManager,
        registry: TypeRegistry | None = None,
        list_caches: dict[str, CacheList] | None = None,
    ) -> None:
        """初始化后台任务管理器

        参数:
            dict_caches: 缓存字典集合
            lock_mgr: 锁管理器
            degrade_mgr: 降级管理器
            backend_mgr: 后端管理器
            registry: 类型注册器（可选）
            list_caches: 缓存列表集合（可选）
        """
        self._dict_caches = dict_caches
        self._list_caches = list_caches or {}
        self._lock_mgr = lock_mgr
        self._degrade_mgr = degrade_mgr
        self._backend_mgr = backend_mgr
        self._registry = registry

    def sync_dict_caches(self, dict_caches: dict[str, CacheDict]) -> None:
        """同步缓存字典集合

        用于运行时动态扩展的缓存字典能够被后台清理任务识别。

        参数:
            dict_caches: 最新的缓存字典集合
        """
        self._dict_caches = dict_caches

    def sync_list_caches(self, list_caches: dict[str, CacheList]) -> None:
        """同步缓存列表集合

        用于运行时动态扩展的缓存列表能够被后台清理任务识别。

        参数:
            list_caches: 最新的缓存列表集合
        """
        self._list_caches = list_caches

    async def _run_periodic(
        self,
        interval: int,
        work: Callable[[], Awaitable[None]],
        label: str,
    ) -> None:
        """通用周期任务运行器

        参数:
            interval: 执行间隔（秒）
            work: 异步工作函数
            label: 任务标签（用于日志）
        """
        while True:
            try:
                await asyncio.sleep(interval)
                await work()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"{label}异常", LOG_COMMAND, e=e)

    async def _cleanup_work(self) -> None:
        """清理过期数据和无效锁的工作函数"""
        dict_tasks = [
            cd.async_cleanup_expired(cache_config.cleanup_batch_size)
            for cd in self._dict_caches.values()
        ]
        list_tasks = [
            cl.async_cleanup_expired(cache_config.cleanup_batch_size)
            for cl in self._list_caches.values()
        ]
        results = await asyncio.gather(*dict_tasks, *list_tasks, return_exceptions=True)
        cleaned = sum(r for r in results if isinstance(r, int))
        if cleaned > 0:
            logger.debug(f"定时清理过期缓存: {cleaned}条", LOG_COMMAND)

        lock_cleaned = self._lock_mgr.cleanup_stale(cache_config.lock_max_age)
        if lock_cleaned > 0:
            logger.debug(f"定时清理过期锁: {lock_cleaned}个", LOG_COMMAND)

    async def _registry_cleanup_work(self) -> None:
        """清理过期键记录的工作函数"""
        if self._registry is None:
            return
        cleaned = self._registry.cleanup_expired_keys()
        if cleaned > 0:
            logger.debug(f"定时清理过期键记录: {cleaned}条", LOG_COMMAND)

    async def _degrade_check_work(self) -> None:
        """降级检测的工作函数"""
        if self._degrade_mgr.degraded:
            recovered = await self._degrade_mgr.try_recover(
                self._backend_mgr.test_connection
            )
            if recovered:
                self._backend_mgr.reset_backend()

    async def _cleanup_loop(self) -> None:
        """定时清理过期数据和无效锁的后台任务"""
        await self._run_periodic(
            cache_config.cleanup_interval, self._cleanup_work, "定时清理任务"
        )

    async def _registry_cleanup_loop(self) -> None:
        """定时清理过期键记录的后台任务"""
        await self._run_periodic(
            cache_config.cleanup_interval, self._registry_cleanup_work, "键记录清理任务"
        )

    async def _degrade_check_loop(self) -> None:
        """定时检测降级恢复的后台任务"""
        await self._run_periodic(
            cache_config.degrade_check_interval,
            self._degrade_check_work,
            "降级检测任务",
        )

    def _init_distributed_lock(self) -> None:
        """初始化分布式锁"""
        try:
            backend = self._backend_mgr.cache_backend
            self._lock_mgr.init_from_backend(backend)
        except Exception as e:
            logger.warning("初始化分布式锁失败", LOG_COMMAND, e=e)

    async def start_all(self) -> list[asyncio.Task]:
        """启动所有后台定时任务

        返回:
            list[asyncio.Task]: 所有后台任务句柄列表
        """
        tasks: list[asyncio.Task] = []

        if cache_config.cleanup_interval > 0:
            cleanup_task = asyncio.create_task(self._cleanup_loop())
            tasks.append(cleanup_task)
            logger.debug(
                f"缓存定时清理任务已启动，间隔: {cache_config.cleanup_interval}秒",
                LOG_COMMAND,
            )

            if self._registry is not None:
                registry_cleanup_task = asyncio.create_task(
                    self._registry_cleanup_loop()
                )
                tasks.append(registry_cleanup_task)
                logger.debug(
                    "键记录定时清理任务已启动，"
                    f"间隔: {cache_config.cleanup_interval}秒",
                    LOG_COMMAND,
                )

        if (
            cache_config.cache_mode == CacheMode.REDIS
            and cache_config.degrade_check_interval > 0
        ):
            degrade_task = asyncio.create_task(self._degrade_check_loop())
            tasks.append(degrade_task)
            self._init_distributed_lock()
            logger.debug(
                "Redis降级检测任务已启动，"
                f"间隔: {cache_config.degrade_check_interval}秒",
                LOG_COMMAND,
            )

        return tasks
