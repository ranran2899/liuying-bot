"""
缓存后端管理器

负责缓存后端的创建、切换和关闭，
支持Redis和内存两种后端，降级时自动切换到内存缓存。
"""

import asyncio
from typing import Any

from aiocache import Cache as AioCache
from aiocache import SimpleMemoryCache
from aiocache.base import BaseCache
from aiocache.serializers import BaseSerializer

from liuying.utils.log import logger

from ..config import CACHE_KEY_PREFIX, LOG_COMMAND, CacheMode, cache_config
from .degrade import DegradeManager

try:
    import orjson as json

    class OrjsonSerializer(BaseSerializer):
        """基于 orjson 的高性能序列化器"""

        encoding = "utf-8"

        def dumps(self, value: object) -> str:
            """序列化值为JSON字符串

            参数:
                value: 需要序列化的值

            返回:
                str: JSON字符串
            """
            if value is None:
                return "null"
            return json.dumps(value).decode(self.encoding)

        def loads(self, value: Any) -> Any:
            """反序列化JSON字符串

            参数:
                value: JSON字符串或字节

            返回:
                Any: 反序列化后的值
            """
            if value is None:
                return None
            if not isinstance(value, str | bytes | bytearray | memoryview):
                return value
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError, ValueError):
                return value

    _DEFAULT_SERIALIZER = OrjsonSerializer
except ImportError:
    from aiocache.serializers import JsonSerializer

    _DEFAULT_SERIALIZER = JsonSerializer  # type: ignore[assignment]


class BackendManager:
    """缓存后端管理器

    负责缓存后端的创建、切换和关闭，
    支持Redis和内存两种后端，降级时自动切换到内存缓存。
    """

    def __init__(self, degrade_mgr: DegradeManager) -> None:
        """初始化后端管理器

        参数:
            degrade_mgr: 降级管理器实例
        """
        self._cache_backend: BaseCache | AioCache | None = None
        self._degrade_mgr = degrade_mgr
        self._close_tasks: set[asyncio.Task] = set()

    @property
    def cache_backend(self) -> BaseCache | AioCache:
        """获取缓存后端，降级时自动切换到内存缓存

        返回:
            BaseCache | AioCache: 缓存后端实例
        """
        if self._degrade_mgr.degraded:
            if self._cache_backend is None or self._is_redis_backend(
                self._cache_backend
            ):
                self._cache_backend = self._create_memory_cache("降级内存缓存")
            return self._cache_backend

        if self._cache_backend is not None:
            return self._cache_backend

        match cache_config.cache_mode:
            case CacheMode.REDIS if cache_config.redis_host:
                try:
                    from aiocache import RedisCache

                    self._cache_backend = RedisCache(
                        serializer=_DEFAULT_SERIALIZER(),
                        namespace=CACHE_KEY_PREFIX,
                        timeout=30,
                        ttl=cache_config.redis_expire,
                        endpoint=cache_config.redis_host,
                        port=cache_config.redis_port,
                        password=cache_config.redis_password,
                    )
                    logger.info(
                        f"使用Redis缓存，地址: {cache_config.redis_host}",
                        LOG_COMMAND,
                    )
                    return self._cache_backend
                except ImportError:
                    logger.warning(
                        "导入aiocache[redis]失败，将默认使用内存缓存",
                        LOG_COMMAND,
                    )
                    self._degrade_mgr.trigger_degrade("aiocache[redis]导入失败")
                    self._cache_backend = self._create_memory_cache("降级内存缓存")
                    return self._cache_backend

            case CacheMode.NONE:
                self._cache_backend = self._create_memory_cache("非持久化内存缓存")
                return self._cache_backend

            case _:
                self._cache_backend = self._create_memory_cache("内存缓存")
                return self._cache_backend

    @property
    def redis_client(self) -> Any | None:
        """获取原生Redis客户端

        返回:
            Any | None: Redis客户端实例或None
        """
        if cache_config.cache_mode != CacheMode.REDIS:
            return None
        backend = self.cache_backend
        if hasattr(backend, "_client"):
            return backend._client
        return None

    def _is_redis_backend(self, backend: BaseCache | AioCache | None) -> bool:
        """检查后端是否为Redis类型

        参数:
            backend: 缓存后端实例

        返回:
            bool: 是否为Redis后端
        """
        if backend is None:
            return False
        return "Redis" in backend.__class__.__name__

    def _create_memory_cache(self, label: str) -> SimpleMemoryCache:
        """创建内存缓存后端

        参数:
            label: 日志标签

        返回:
            SimpleMemoryCache: 内存缓存实例
        """
        self._close_old_backend_async()
        is_none_mode = cache_config.cache_mode == CacheMode.NONE
        ttl = 0 if is_none_mode else cache_config.redis_expire
        logger.info(f"使用{label}", LOG_COMMAND)
        return SimpleMemoryCache(
            serializer=_DEFAULT_SERIALIZER(),
            namespace=CACHE_KEY_PREFIX,
            timeout=30,
            ttl=ttl,
        )

    def _schedule_close(self, backend: BaseCache | AioCache) -> None:
        """安全调度异步关闭后端连接，持有任务引用防止GC回收

        参数:
            backend: 要关闭的后端实例
        """
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(self._safe_close_backend(backend))
            self._close_tasks.add(task)
            task.add_done_callback(self._close_tasks.discard)
        except RuntimeError:
            pass

    def _close_old_backend_async(self) -> None:
        """异步关闭旧的后端连接"""
        if self._cache_backend is not None and self._is_redis_backend(
            self._cache_backend
        ):
            self._schedule_close(self._cache_backend)

    async def _safe_close_backend(self, backend: BaseCache | AioCache) -> None:
        """安全关闭后端连接

        参数:
            backend: 要关闭的后端实例
        """
        try:
            await backend.close()
        except Exception as e:
            logger.debug("关闭旧缓存连接", LOG_COMMAND, e=e)

    def reset_backend(self) -> None:
        """重置缓存后端（降级恢复后调用，使下次访问重新创建后端）"""
        if self._cache_backend is not None:
            self._schedule_close(self._cache_backend)
        self._cache_backend = None

    async def test_connection(self) -> bool:
        """测试Redis连接是否可用

        当前后端为Redis时复用其连接；降级后当前后端为内存缓存时，
        创建临时Redis连接探测，避免误判内存缓存成功为Redis恢复。

        返回:
            bool: Redis连接是否可用
        """
        if cache_config.cache_mode != CacheMode.REDIS:
            return True
        backend = self._cache_backend
        if backend is not None and self._is_redis_backend(backend):
            try:
                await backend.set("__degrade_check__", "1", ttl=5)
                result = await backend.get("__degrade_check__")
                await backend.delete("__degrade_check__")
                return result is not None
            except Exception as e:
                logger.debug("Redis连接测试失败", LOG_COMMAND, e=e)
                return False
        return await self._test_redis_via_temp_connection()

    async def _test_redis_via_temp_connection(self) -> bool:
        """创建临时Redis连接测试可用性

        用于降级状态下（当前后端为内存缓存）检测Redis是否恢复。

        返回:
            bool: Redis连接是否可用
        """
        try:
            from aiocache import RedisCache

            test_cache = RedisCache(
                endpoint=cache_config.redis_host,
                port=cache_config.redis_port,
                password=cache_config.redis_password,
                namespace=CACHE_KEY_PREFIX,
            )
            try:
                await test_cache.set("__degrade_check__", "1", ttl=5)
                result = await test_cache.get("__degrade_check__")
                await test_cache.delete("__degrade_check__")
                return result is not None
            finally:
                try:
                    await test_cache.close()
                except Exception as e:
                    logger.debug("关闭临时测试连接失败", LOG_COMMAND, e=e)
        except Exception as e:
            logger.debug("创建临时Redis连接失败", LOG_COMMAND, e=e)
            return False

    async def close(self) -> None:
        """关闭缓存连接"""
        if self._cache_backend:
            try:
                await self._cache_backend.close()
            except Exception as e:
                logger.warning("关闭缓存连接失败", LOG_COMMAND, e=e)
            self._cache_backend = None
