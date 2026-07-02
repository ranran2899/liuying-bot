"""
缓存单条操作

提供类型化和原始键两种单条缓存操作，包括获取、设置、删除、存在性检查，
以及击穿防护获取和统一的异常处理。
"""

import asyncio
from collections.abc import Callable
import random
import time
from typing import TYPE_CHECKING, Any, ClassVar

from liuying.utils.log import logger

from ..config import (
    CACHE_KEY_PREFIX,
    CACHE_KEY_SEPARATOR,
    CACHE_TIMEOUT_SECONDS,
    LOG_COMMAND,
    CacheException,
    KeyType,
    cache_config,
)
from ..monitor import CacheMonitor
from ..serializer import CacheSerializer, DeserializationError, SerializationError
from .backend import BackendManager
from .lock import LockManager
from .registry import TypeRegistry

if TYPE_CHECKING:
    from .degrade import DegradeManager


class CacheOperations:
    """缓存单条操作执行器

    封装类型化和原始键的单条缓存操作，持有后端、注册器、监控、降级、锁等依赖，
    避免每次调用都传来传去。支持雪崩防护、击穿防护和统一异常处理。
    """

    RAW_TYPE: ClassVar[str] = "__RAW__"
    """原始键操作的监控类型标识"""

    def __init__(
        self,
        backend_mgr: BackendManager,
        registry: TypeRegistry,
        monitor: CacheMonitor,
        degrade_mgr: "DegradeManager",
        lock_mgr: LockManager,
    ) -> None:
        """初始化缓存操作执行器

        参数:
            backend_mgr: 后端管理器
            registry: 类型注册器
            monitor: 缓存监控器
            degrade_mgr: 降级管理器
            lock_mgr: 锁管理器
        """
        self._backend_mgr = backend_mgr
        self._registry = registry
        self._monitor = monitor
        self._degrade_mgr = degrade_mgr
        self._lock_mgr = lock_mgr

    @staticmethod
    def _is_serialization_error(exc: Exception) -> bool:
        """判断异常是否为序列化相关错误

        参数:
            exc: 异常实例

        返回:
            bool: 是否为序列化错误
        """
        return isinstance(
            exc,
            SerializationError | DeserializationError | ValueError | TypeError,
        )

    @staticmethod
    def _resolve_cache_type(registry: TypeRegistry, cache_type: str) -> str | None:
        """解析并校验缓存类型

        参数:
            registry: 类型注册器
            cache_type: 原始缓存类型字符串

        返回:
            str | None: 大写且已注册的缓存类型，无效时返回None
        """
        name = cache_type.upper()
        return name if registry.is_valid(name) else None

    @staticmethod
    def _build_raw_key(key_value: str, namespace: str | None = None) -> str:
        """构建原始键完整缓存键

        参数:
            key_value: 原始键值
            namespace: 命名空间

        返回:
            str: 完整缓存键
        """
        parts = [CACHE_KEY_PREFIX]
        if namespace:
            parts.append(namespace)
        parts.append(key_value)
        return CACHE_KEY_SEPARATOR.join(parts)

    def _handle_operation_error(
        self,
        cache_type: str,
        cache_key: str | None,
        operation: str,
        exc: Exception,
    ) -> None:
        """处理缓存操作异常的通用逻辑

        参数:
            cache_type: 缓存类型
            cache_key: 缓存键
            operation: 操作名称
            exc: 异常实例
        """
        self._monitor.record_error(cache_type)
        if not self._is_serialization_error(exc):
            self._degrade_mgr.record_failure()
        match exc:
            case TimeoutError():
                logger.warning(
                    f"{operation}缓存 {cache_type}:{cache_key} 超时",
                    LOG_COMMAND,
                )
            case CacheException():
                logger.warning(f"{operation}缓存失败", LOG_COMMAND, e=exc)
            case _:
                logger.warning(f"{operation}缓存 {cache_type} 失败", LOG_COMMAND, e=exc)

    @staticmethod
    def calc_jitter_ttl(base_ttl: int) -> int:
        """计算带随机偏移的TTL，用于雪崩防护

        参数:
            base_ttl: 基础过期时间（秒）

        返回:
            int: 添加随机偏移后的过期时间
        """
        jitter = cache_config.avalanche_jitter
        if jitter <= 0 or base_ttl <= 0:
            return base_ttl
        offset = random.randint(0, min(jitter, base_ttl // 2))
        return base_ttl + offset

    async def get(
        self,
        cache_type: str,
        key: KeyType,
        default: Any = None,
        namespace: str | None = None,
    ) -> Any:
        """获取类型化缓存数据

        参数:
            cache_type: 缓存类型
            key: 键或键参数
            default: 默认值
            namespace: 可选的命名空间

        返回:
            Any: 缓存数据，如果不存在返回默认值
        """
        resolved_type = self._resolve_cache_type(self._registry, cache_type)
        if resolved_type is None:
            return default

        cache_key = None
        start_time = time.time()
        try:
            cache_key = self._registry.build_key(resolved_type, key, namespace)
            data = await asyncio.wait_for(
                self._backend_mgr.cache_backend.get(cache_key),
                timeout=CACHE_TIMEOUT_SECONDS,
            )
            elapsed = time.time() - start_time

            if data is None:
                self._monitor.record_miss(resolved_type, elapsed)
                return default

            self._monitor.record_hit(resolved_type, elapsed)
            self._degrade_mgr.record_success()

            model = self._registry.get_model(resolved_type)
            result_type = model.result_type
            return (
                CacheSerializer.deserialize(data, result_type)
                if result_type
                else data
            )
        except Exception as e:
            self._handle_operation_error(resolved_type, cache_key, "获取", e)
            return default

    async def set(
        self,
        cache_type: str,
        key: KeyType,
        value: Any,
        expire: int | None = None,
        namespace: str | None = None,
    ) -> bool:
        """设置类型化缓存数据，自动添加雪崩防护的随机偏移

        参数:
            cache_type: 缓存类型
            key: 键或键参数
            value: 值
            expire: 过期时间（秒），为None时使用默认值
            namespace: 可选的命名空间

        返回:
            bool: 是否成功
        """
        resolved_type = self._resolve_cache_type(self._registry, cache_type)
        if resolved_type is None:
            return False

        cache_key = None
        start_time = time.time()
        try:
            cache_key = self._registry.build_key(resolved_type, key, namespace)
            model = self._registry.get_model(resolved_type)

            serialized_value = CacheSerializer.serialize(value)
            base_ttl = expire if expire is not None else model.expire
            ttl = self.calc_jitter_ttl(base_ttl)

            await asyncio.wait_for(
                self._backend_mgr.cache_backend.set(
                    cache_key, serialized_value, ttl=ttl
                ),
                timeout=CACHE_TIMEOUT_SECONDS,
            )
            self._registry.add_key(resolved_type, cache_key, ttl)
            elapsed = time.time() - start_time
            self._monitor.record_set(resolved_type, elapsed)
            self._degrade_mgr.record_success()
            return True
        except Exception as e:
            self._handle_operation_error(resolved_type, cache_key, "设置", e)
            return False

    async def delete(
        self,
        cache_type: str,
        key: KeyType,
        namespace: str | None = None,
    ) -> bool:
        """删除类型化缓存数据

        参数:
            cache_type: 缓存类型
            key: 键或键参数
            namespace: 可选的命名空间

        返回:
            bool: 是否成功
        """
        resolved_type = self._resolve_cache_type(self._registry, cache_type)
        if resolved_type is None:
            return False

        cache_key: str | None = None
        start_time = time.time()
        try:
            cache_key = self._registry.build_key(resolved_type, key, namespace)
            await asyncio.wait_for(
                self._backend_mgr.cache_backend.delete(cache_key),
                timeout=CACHE_TIMEOUT_SECONDS,
            )
            self._registry.remove_key(resolved_type, cache_key)
            self._lock_mgr.remove_lock(f"lock:{cache_key}")
            elapsed = time.time() - start_time
            self._monitor.record_delete(resolved_type, elapsed)
            self._degrade_mgr.record_success()
            return True
        except Exception as e:
            self._handle_operation_error(resolved_type, cache_key, "删除", e)
            return False

    async def exists(
        self,
        cache_type: str,
        key: KeyType,
        namespace: str | None = None,
    ) -> bool:
        """检查类型化缓存是否存在

        参数:
            cache_type: 缓存类型
            key: 键或键参数
            namespace: 可选的命名空间

        返回:
            bool: 是否存在
        """
        resolved_type = self._resolve_cache_type(self._registry, cache_type)
        if resolved_type is None:
            return False

        cache_key: str | None = None
        try:
            cache_key = self._registry.build_key(resolved_type, key, namespace)
            exists_result = await asyncio.wait_for(
                self._backend_mgr.cache_backend.exists(cache_key),
                timeout=CACHE_TIMEOUT_SECONDS,
            )
            if exists_result:
                self._degrade_mgr.record_success()
            return bool(exists_result)
        except Exception as e:
            self._handle_operation_error(resolved_type, cache_key, "检查", e)
            return False

    async def _get_silent(
        self,
        cache_type: str,
        cache_key: str,
    ) -> Any:
        """静默获取缓存数据（不记录监控指标）

        用于击穿防护的第二次检查，避免同一 key 的监控指标重复计数。
        仍然记录降级成功/失败，保证降级机制正常工作。

        参数:
            cache_type: 缓存类型（已校验）
            cache_key: 完整缓存键

        返回:
            Any: 缓存数据，如果不存在返回None
        """
        try:
            data = await asyncio.wait_for(
                self._backend_mgr.cache_backend.get(cache_key),
                timeout=CACHE_TIMEOUT_SECONDS,
            )
            if data is None:
                return None
            self._degrade_mgr.record_success()
            model = self._registry.get_model(cache_type)
            result_type = model.result_type
            return (
                CacheSerializer.deserialize(data, result_type)
                if result_type
                else data
            )
        except Exception as e:
            self._handle_operation_error(cache_type, cache_key, "获取", e)
            return None

    async def get_with_stampede(
        self,
        cache_type: str,
        key: KeyType,
        loader: Callable[..., Any],
        expire: int | None = None,
        default: Any = None,
        namespace: str | None = None,
    ) -> Any:
        """带击穿防护的获取类型化缓存数据

        使用双重检查锁定模式防止缓存击穿：
        1. 首先尝试获取缓存（记录监控）
        2. 未命中时获取锁，再次检查缓存（不记录监控，避免重复计数）
        3. 仍然未命中时执行loader加载数据

        参数:
            cache_type: 缓存类型
            key: 键或键参数
            loader: 数据加载函数（异步）
            expire: 过期时间（秒）
            default: 默认值
            namespace: 可选的命名空间

        返回:
            Any: 缓存数据或loader加载的数据
        """
        resolved_type = self._resolve_cache_type(self._registry, cache_type)
        if resolved_type is None:
            try:
                loaded = await loader()
                return loaded if loaded is not None else default
            except Exception as e:
                logger.warning("击穿防护loader执行失败", LOG_COMMAND, e=e)
                return default

        # 第一次检查（记录监控指标）
        result = await self.get(cache_type, key, None, namespace)
        if result is not None:
            return result

        # 构建锁键（带 namespace 隔离，避免不同命名空间相同key共享锁）
        cache_key = self._registry.build_key(resolved_type, key, namespace)
        lock = self._lock_mgr.get_lock(f"lock:{cache_key}")

        acquired = await lock.acquire(
            timeout_seconds=cache_config.stampede_lock_timeout
        )
        if not acquired:
            logger.warning("击穿防护获取锁超时，直接返回默认值", LOG_COMMAND)
            return default

        try:
            # 第二次检查（静默，不记录监控，避免重复计数）
            result = await self._get_silent(resolved_type, cache_key)
            if result is not None:
                return result

            try:
                loaded = await loader()
                if loaded is not None:
                    await self.set(cache_type, key, loaded, expire, namespace)
                return loaded if loaded is not None else default
            except Exception as e:
                logger.warning("击穿防护loader执行失败", LOG_COMMAND, e=e)
                return default
        finally:
            await lock.release()

    async def raw_get(
        self,
        key: str,
        default: Any = None,
        namespace: str | None = None,
    ) -> Any:
        """获取原始键缓存数据

        参数:
            key: 原始缓存键
            default: 默认值
            namespace: 可选的命名空间

        返回:
            Any: 缓存数据，如果不存在返回默认值
        """
        cache_key = self._build_raw_key(key, namespace)
        start_time = time.time()
        try:
            data = await asyncio.wait_for(
                self._backend_mgr.cache_backend.get(cache_key),
                timeout=CACHE_TIMEOUT_SECONDS,
            )
            elapsed = time.time() - start_time
            if data is None:
                self._monitor.record_miss(self.RAW_TYPE, elapsed)
                return default
            self._monitor.record_hit(self.RAW_TYPE, elapsed)
            self._degrade_mgr.record_success()
            return CacheSerializer.deserialize(data)
        except Exception as e:
            self._handle_operation_error(self.RAW_TYPE, cache_key, "获取", e)
            return default

    async def raw_set(
        self,
        key: str,
        value: Any,
        expire: int | None = None,
        namespace: str | None = None,
    ) -> bool:
        """设置原始键缓存数据

        参数:
            key: 原始缓存键
            value: 值
            expire: 过期时间（秒）
            namespace: 可选的命名空间

        返回:
            bool: 是否成功
        """
        cache_key = self._build_raw_key(key, namespace)
        start_time = time.time()
        try:
            serialized_value = CacheSerializer.serialize(value)
            base_expire = expire if expire is not None else cache_config.redis_expire
            ttl = self.calc_jitter_ttl(base_expire)
            await asyncio.wait_for(
                self._backend_mgr.cache_backend.set(
                    cache_key, serialized_value, ttl=ttl
                ),
                timeout=CACHE_TIMEOUT_SECONDS,
            )
            elapsed = time.time() - start_time
            self._monitor.record_set(self.RAW_TYPE, elapsed)
            self._degrade_mgr.record_success()
            return True
        except Exception as e:
            self._handle_operation_error(self.RAW_TYPE, cache_key, "设置", e)
            return False

    async def raw_delete(
        self,
        key: str,
        namespace: str | None = None,
    ) -> bool:
        """删除原始键缓存数据

        参数:
            key: 原始缓存键
            namespace: 可选的命名空间

        返回:
            bool: 是否成功
        """
        cache_key = self._build_raw_key(key, namespace)
        start_time = time.time()
        try:
            await self._backend_mgr.cache_backend.delete(cache_key)
            self._lock_mgr.remove_lock(f"lock:{cache_key}")
            elapsed = time.time() - start_time
            self._monitor.record_delete(self.RAW_TYPE, elapsed)
            self._degrade_mgr.record_success()
            return True
        except Exception as e:
            self._handle_operation_error(self.RAW_TYPE, cache_key, "删除", e)
            return False

    async def raw_exists(
        self,
        key: str,
        namespace: str | None = None,
    ) -> bool:
        """检查原始键缓存是否存在

        参数:
            key: 原始缓存键
            namespace: 可选的命名空间

        返回:
            bool: 是否存在
        """
        cache_key = self._build_raw_key(key, namespace)
        try:
            exists_result = await asyncio.wait_for(
                self._backend_mgr.cache_backend.exists(cache_key),
                timeout=CACHE_TIMEOUT_SECONDS,
            )
            if exists_result:
                self._degrade_mgr.record_success()
            return bool(exists_result)
        except Exception as e:
            self._handle_operation_error(self.RAW_TYPE, cache_key, "检查", e)
            return False
