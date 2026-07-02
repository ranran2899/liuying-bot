"""
缓存管理器核心

支持雪崩防护（随机过期偏移）、击穿防护（分布式锁）、
Redis降级检测、定时过期清理、缓存预热和Pipeline优化。
通过组合 BackendManager、TypeRegistry、DegradeManager、LockManager 和
各功能执行器（CacheOperations/BatchExecutor/PipelineExecutor/WarmupExecutor/BackgroundTaskManager）
实现职责分离。
"""

import asyncio
from collections.abc import Callable
from threading import Lock
from typing import Any, ClassVar, Self

from liuying.utils.log import logger

from ..config import LOG_COMMAND, CacheException, CacheMode, KeyType, cache_config
from ..containers.dict import CacheDict
from ..containers.list import CacheList
from ..monitor import CacheMonitor
from .backend import BackendManager
from .batch import BatchExecutor, BatchResult
from .degrade import DegradeManager
from .lock import LockManager
from .operations import CacheOperations
from .pipeline import PipelineExecutor
from .registry import TypeRegistry
from .tasks import BackgroundTaskManager
from .warmup import WarmupExecutor, WarmupResult


class CacheManager:
    """缓存管理器

    支持雪崩防护（随机过期偏移）、击穿防护（分布式锁）、
    批量操作并发控制、Redis降级检测、定时过期清理、
    缓存预热和Pipeline优化。
    通过组合各执行器实现职责分离，避免散装函数参数传来传去。
    """

    _instance: ClassVar[Self | None] = None
    _init_lock: ClassVar[Lock] = Lock()
    _monitor: ClassVar[CacheMonitor] = CacheMonitor()

    def __new__(cls) -> Self:
        """单例模式（线程安全）"""
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._degrade_mgr = DegradeManager()
                    instance._backend_mgr = BackendManager(instance._degrade_mgr)
                    instance._registry = TypeRegistry()
                    instance._lock_mgr = LockManager(
                        lock_ttl=cache_config.lock_ttl,
                        cleanup_interval=cache_config.cleanup_interval,
                    )
                    instance._cache_ops = CacheOperations(
                        instance._backend_mgr,
                        instance._registry,
                        cls._monitor,
                        instance._degrade_mgr,
                        instance._lock_mgr,
                    )
                    instance._batch_executor = BatchExecutor(
                        instance._registry,
                        instance._cache_ops,
                    )
                    instance._pipeline_executor = PipelineExecutor(
                        instance._backend_mgr,
                        instance._registry,
                        instance._batch_executor,
                    )
                    instance._warmup_executor = WarmupExecutor(
                        instance._cache_ops,
                        instance._registry,
                        enabled=True,
                    )
                    instance._dict_caches: dict[str, CacheDict] = {}
                    instance._list_caches: dict[str, CacheList] = {}
                    instance._task_manager = BackgroundTaskManager(
                        instance._dict_caches,
                        instance._lock_mgr,
                        instance._degrade_mgr,
                        instance._backend_mgr,
                        instance._registry,
                        instance._list_caches,
                    )
                    instance._enabled: bool = False
                    instance._batch_semaphore: asyncio.Semaphore | None = None
                    instance._background_tasks: list[asyncio.Task] = []
                    cls._instance = instance
        return cls._instance

    @property
    def enabled(self) -> bool:
        """获取缓存启用状态"""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """设置缓存启用状态"""
        self._enabled = value

    @property
    def degraded(self) -> bool:
        """获取降级状态"""
        return self._degrade_mgr.degraded

    @property
    def degrade_info(self) -> dict[str, Any]:
        """获取降级信息"""
        return self._degrade_mgr.degrade_info

    @property
    def namespace(self) -> str:
        """获取当前命名空间"""
        return self._registry.namespace

    @namespace.setter
    def namespace(self, value: str) -> None:
        """设置命名空间"""
        self._registry.namespace = value

    def enable(self) -> None:
        """启用缓存"""
        self._enabled = True
        logger.info("缓存功能已启用", LOG_COMMAND)

    def disable(self) -> None:
        """禁用缓存"""
        self._enabled = False
        logger.info("缓存功能已禁用", LOG_COMMAND)

    def set_namespace(self, namespace: str) -> None:
        """设置命名空间（用于运行时切换租户）

        参数:
            namespace: 命名空间
        """
        self._registry.set_namespace(namespace)
        logger.info(f"缓存命名空间已设置为: {namespace}", LOG_COMMAND)

    def clear_namespace(self) -> None:
        """清除命名空间"""
        self._registry.clear_namespace()
        logger.info("缓存命名空间已清除", LOG_COMMAND)

    def _check_enabled_and_mode(self) -> bool:
        """检查缓存是否启用且不是NONE模式"""
        return self._enabled and cache_config.cache_mode != CacheMode.NONE

    def _get_batch_semaphore(self) -> asyncio.Semaphore:
        """获取批量操作信号量"""
        if self._batch_semaphore is None:
            self._batch_semaphore = asyncio.Semaphore(
                cache_config.batch_concurrency_limit
            )
        return self._batch_semaphore

    def cache_dict(self, cache_type: str, expire: int = 0) -> CacheDict:
        """获取缓存字典

        参数:
            cache_type: 缓存类型
            expire: 过期时间（秒）

        返回:
            CacheDict: 缓存字典实例
        """
        name = cache_type.upper()
        if name not in self._dict_caches:
            self._dict_caches[name] = CacheDict(
                name, expire, cache_config.memory_cache_max_size
            )
        return self._dict_caches[name]

    def cache_list(self, cache_type: str, expire: int = 0) -> CacheList:
        """获取缓存列表

        参数:
            cache_type: 缓存类型
            expire: 过期时间（秒）

        返回:
            CacheList: 缓存列表实例
        """
        name = cache_type.upper()
        if name not in self._list_caches:
            self._list_caches[name] = CacheList(
                name, expire, cache_config.memory_cache_max_size
            )
        return self._list_caches[name]

    def register(
        self,
        name: str,
        result_type: type | None = None,
        expire: int = 600,
        key_format: str | None = None,
    ) -> None:
        """注册缓存类型

        参数:
            name: 缓存名称
            result_type: 结果类型
            expire: 过期时间（秒）
            key_format: 键格式
        """
        self._registry.register(name, result_type, expire, key_format)

    def get_model(self, name: str) -> Any:
        """获取缓存模型

        参数:
            name: 缓存名称

        返回:
            CacheModel: 缓存模型
        """
        return self._registry.get_model(name)

    async def get(
        self,
        cache_type: str,
        key: KeyType,
        default: Any = None,
        namespace: str | None = None,
    ) -> Any:
        """获取缓存数据"""
        if not self._check_enabled_and_mode():
            return default
        return await self._cache_ops.get(cache_type, key, default, namespace)

    async def set(
        self,
        cache_type: str,
        key: KeyType,
        value: Any,
        expire: int | None = None,
        namespace: str | None = None,
    ) -> bool:
        """设置缓存数据"""
        if not self._check_enabled_and_mode():
            return False
        return await self._cache_ops.set(cache_type, key, value, expire, namespace)

    async def delete(
        self, cache_type: str, key: KeyType, namespace: str | None = None
    ) -> bool:
        """删除缓存数据"""
        if not self._check_enabled_and_mode():
            return False
        return await self._cache_ops.delete(cache_type, key, namespace)

    async def exists(
        self, cache_type: str, key: KeyType, namespace: str | None = None
    ) -> bool:
        """检查缓存是否存在"""
        if not self._check_enabled_and_mode():
            return False
        return await self._cache_ops.exists(cache_type, key, namespace)

    async def get_with_stampede(
        self,
        cache_type: str,
        key: KeyType,
        loader: Callable[..., Any],
        expire: int | None = None,
        default: Any = None,
        namespace: str | None = None,
    ) -> Any:
        """带击穿防护的获取缓存数据"""
        if not self._check_enabled_and_mode():
            try:
                loaded = await loader()
                return loaded if loaded is not None else default
            except Exception:
                return default
        return await self._cache_ops.get_with_stampede(
            cache_type, key, loader, expire, default, namespace
        )

    async def raw_get(
        self, key: str, default: Any = None, namespace: str | None = None
    ) -> Any:
        """获取原始键缓存数据"""
        if not self._check_enabled_and_mode():
            return default
        return await self._cache_ops.raw_get(key, default, namespace)

    async def raw_set(
        self,
        key: str,
        value: Any,
        expire: int | None = None,
        namespace: str | None = None,
    ) -> bool:
        """设置原始键缓存数据"""
        if not self._check_enabled_and_mode():
            return False
        return await self._cache_ops.raw_set(key, value, expire, namespace)

    async def raw_delete(self, key: str, namespace: str | None = None) -> bool:
        """删除原始键缓存数据"""
        if not self._check_enabled_and_mode():
            return False
        return await self._cache_ops.raw_delete(key, namespace)

    async def raw_exists(self, key: str, namespace: str | None = None) -> bool:
        """检查原始键缓存是否存在"""
        if not self._check_enabled_and_mode():
            return False
        return await self._cache_ops.raw_exists(key, namespace)

    async def clear(self, cache_type: str | None = None) -> bool:
        """清除缓存

        参数:
            cache_type: 缓存类型，为None时清除所有缓存

        返回:
            bool: 是否成功
        """
        if not self._check_enabled_and_mode():
            return False

        try:
            match cache_type:
                case None:
                    await self._backend_mgr.cache_backend.clear()
                    self._registry.clear_all_keys()
                    self._lock_mgr.clear()
                    return True
                case _:
                    resolved_type = cache_type.upper()
                    if not self._registry.is_valid(resolved_type):
                        return False
                    keys = self._registry.pop_keys(resolved_type).copy()

                    async def _delete_one(cache_key: str) -> bool:
                        try:
                            await self._backend_mgr.cache_backend.delete(cache_key)
                            self._lock_mgr.remove_lock(f"lock:{cache_key}")
                            return True
                        except Exception as e:
                            logger.debug(
                                f"清除缓存键失败: {cache_key}",
                                LOG_COMMAND,
                                e=e,
                            )
                            return False

                    results = await asyncio.gather(
                        *(_delete_one(k) for k in keys),
                        return_exceptions=True,
                    )
                    cleaned = sum(1 for r in results if r is True)
                    logger.debug(
                        f"已清除 {resolved_type} 类型的 {cleaned}/{len(keys)} 个缓存",
                        LOG_COMMAND,
                    )
                    return True
        except Exception as e:
            logger.warning("清除缓存失败", LOG_COMMAND, e=e)
            return False

    async def invalidate_cache(
        self, cache_type: str, key: KeyType | None = None
    ) -> bool:
        """使指定类型的缓存失效

        参数:
            cache_type: 缓存类型
            key: 缓存键或键参数，为None时清除该类型的所有缓存

        返回:
            bool: 是否成功
        """
        if not self._check_enabled_and_mode():
            return True

        resolved_type = cache_type.upper()
        if not self._registry.is_valid(resolved_type):
            return True

        try:
            match key:
                case None:
                    logger.debug(f"清除所有 {resolved_type} 缓存", LOG_COMMAND)
                    return await self.clear(resolved_type)
                case _:
                    cache_key = self._registry.build_key(resolved_type, key)
                    await self._backend_mgr.cache_backend.delete(cache_key)
                    self._registry.remove_key(resolved_type, cache_key)
                    self._lock_mgr.remove_lock(f"lock:{cache_key}")
                    logger.debug(f"清除缓存: {resolved_type}, 键: {key}", LOG_COMMAND)
                    return True
        except CacheException as e:
            logger.warning("清除缓存失败", LOG_COMMAND, e=e)
            return False
        except Exception as e:
            logger.warning(f"清除缓存 {resolved_type} 失败", LOG_COMMAND, e=e)
            return False

    async def invalidate_namespace(self, namespace: str) -> int:
        """使指定命名空间的所有缓存失效

        参数:
            namespace: 命名空间

        返回:
            int: 清除的缓存数量
        """
        if not self._check_enabled_and_mode():
            return 0

        ns_keys = self._registry.get_keys_by_namespace(namespace)

        async def _delete_one(ct: str, ck: str) -> bool:
            try:
                await self._backend_mgr.cache_backend.delete(ck)
                self._registry.remove_key(ct, ck)
                self._lock_mgr.remove_lock(f"lock:{ck}")
                return True
            except Exception as e:
                logger.debug(
                    f"清除命名空间缓存键失败: {ck}",
                    LOG_COMMAND,
                    e=e,
                )
                return False

        tasks = [
            _delete_one(ct, ck)
            for ct, keys in ns_keys.items()
            for ck in keys
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_cleared = sum(1 for r in results if r is True)

        self._registry.clear_namespace_keys(namespace)
        logger.info(
            f"已清除命名空间 {namespace} 的 {total_cleared} 个缓存",
            LOG_COMMAND,
        )
        return total_cleared

    async def multi_get(self, cache_type: str, keys: list[KeyType]) -> BatchResult:
        """批量获取缓存数据"""
        if not self._check_enabled_and_mode():
            return BatchExecutor.make_disabled_result(len(keys), "缓存未启用")
        return await self._batch_executor.multi_get(
            cache_type,
            keys,
            self._cache_ops.get,
            self._get_batch_semaphore(),
        )

    async def multi_set(
        self,
        cache_type: str,
        items: dict[KeyType, Any],
        expire: int | None = None,
    ) -> BatchResult:
        """批量设置缓存数据"""
        if not self._check_enabled_and_mode():
            return BatchExecutor.make_disabled_result(len(items), "缓存未启用")
        return await self._batch_executor.multi_set(
            cache_type,
            items,
            self._cache_ops.set,
            expire,
            self._get_batch_semaphore(),
        )

    async def multi_delete(
        self, cache_type: str, keys: list[KeyType]
    ) -> BatchResult:
        """批量删除缓存数据"""
        if not self._check_enabled_and_mode():
            return BatchExecutor.make_disabled_result(len(keys), "缓存未启用")
        return await self._batch_executor.multi_delete(
            cache_type,
            keys,
            self._cache_ops.delete,
            self._get_batch_semaphore(),
        )

    async def multi_get_pipeline(
        self, cache_type: str, keys: list[KeyType]
    ) -> BatchResult:
        """使用Pipeline批量获取缓存数据"""
        if not self._check_enabled_and_mode():
            return BatchExecutor.make_disabled_result(len(keys), "缓存未启用")
        return await self._pipeline_executor.multi_get(
            cache_type, keys, self._cache_ops.get
        )

    async def multi_set_pipeline(
        self, cache_type: str, items: dict[KeyType, Any], expire: int | None = None
    ) -> BatchResult:
        """使用Pipeline批量设置缓存数据"""
        if not self._check_enabled_and_mode():
            return BatchExecutor.make_disabled_result(len(items), "缓存未启用")
        return await self._pipeline_executor.multi_set(
            cache_type, items, self._cache_ops.set, expire
        )

    async def warmup(
        self,
        cache_type: str,
        loader: Callable[..., Any],
        keys: list[KeyType] | None = None,
        expire: int | None = None,
        batch_size: int | None = None,
    ) -> WarmupResult:
        """缓存预热"""
        self._warmup_executor.set_enabled(self._check_enabled_and_mode())
        return await self._warmup_executor.warmup(
            cache_type, loader, keys, expire, batch_size
        )

    @property
    def stats(self) -> dict[str, Any]:
        """获取缓存统计信息"""
        return {
            "enabled": self._enabled,
            "cache_mode": cache_config.cache_mode,
            "namespace": self._registry.namespace,
            "registered_types": self._registry.registered_count,
            "dict_caches": len(self._dict_caches),
            "list_caches": len(self._list_caches),
            "lock_count": self._lock_mgr.lock_count,
            "degrade_info": self._degrade_mgr.degrade_info,
            "monitor": self._monitor.get_report(),
        }

    @property
    def monitor(self) -> CacheMonitor:
        """获取缓存监控器"""
        return self._monitor

    async def close(self) -> None:
        """关闭缓存连接"""
        for task in self._background_tasks:
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()
        self._lock_mgr.clear()
        await self._backend_mgr.close()

    async def start_background_tasks(self) -> None:
        """启动后台定时任务"""
        # 先取消并等待旧任务结束，避免重复运行
        for task in self._background_tasks:
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        # 同步任务管理器的依赖（dict_caches/list_caches 可能已被动态扩展）
        self._task_manager.sync_dict_caches(self._dict_caches)
        self._task_manager.sync_list_caches(self._list_caches)
        self._background_tasks = await self._task_manager.start_all()


CacheRoot = CacheManager()
