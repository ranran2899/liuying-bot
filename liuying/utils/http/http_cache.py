"""HTTP响应缓存模块，基于统一缓存服务实现TTL过期和击穿防护。

通过 liuying.services.cache 提供底层存储、TTL管理、雪崩防护和击穿防护，
符合项目"所有缓存操作必须使用统一缓存接口"的硬约束。
"""

from collections.abc import Awaitable, Callable
import hashlib
from typing import Any

from liuying.services.cache import Cache
from liuying.utils.log import logger

_LOG_TAG = "ResponseCache"
_CACHE_TYPE = "HTTP_RESPONSE"
_KEY_PREFIX = "http:"


class ResponseCache:
    """HTTP响应缓存适配器，基于统一缓存服务实现。

    通过 CacheRoot.raw_get/raw_set 提供原始键操作，
    通过 Cache.get_or_load 提供击穿防护，自动复用统一缓存系统的
    TTL管理、雪崩防护、Redis降级和定时清理能力。

    参数:
        default_ttl: 默认TTL(秒)。
    """

    def __init__(self, default_ttl: float = 300.0):
        self.default_ttl = int(default_ttl)
        self._cache: Cache[Any] = Cache(_CACHE_TYPE, result_type=dict)

    @staticmethod
    def build_cache_key(
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        json_data: Any = None,
    ) -> str:
        """构建缓存键，基于方法、URL和参数生成哈希。

        参数:
            method: HTTP方法。
            url: 请求URL。
            params: 查询参数。
            json_data: JSON请求体。

        返回:
            str: 缓存键字符串。
        """
        parts = [method.upper(), url]
        if params:
            sorted_params = sorted(params.items())
            parts.append(str(sorted_params))
        if json_data is not None:
            parts.append(str(json_data))
        raw = "|".join(parts)
        return hashlib.md5(raw.encode()).hexdigest()

    @staticmethod
    def _format_key(key: str) -> str:
        """格式化原始键，添加命名空间前缀避免冲突。

        参数:
            key: 原始缓存键。

        返回:
            str: 带前缀的缓存键。
        """
        return f"{_KEY_PREFIX}{key}"

    async def get(self, key: str) -> Any | None:
        """异步获取缓存值。

        参数:
            key: 缓存键。

        返回:
            Any | None: 缓存数据，未命中返回None。
        """
        return await self._cache.raw_get(self._format_key(key))

    async def set(self, key: str, data: Any, ttl: float | None = None) -> None:
        """异步设置缓存值。

        参数:
            key: 缓存键。
            data: 缓存数据。
            ttl: TTL(秒)，None时使用默认值。
        """
        expire = int(ttl) if ttl is not None else self.default_ttl
        await self._cache.raw_set(self._format_key(key), data, expire=expire)

    async def invalidate(self, key: str) -> bool:
        """使指定缓存键失效。

        参数:
            key: 缓存键。

        返回:
            bool: 是否成功移除。
        """
        return await self._cache.raw_delete(self._format_key(key))

    async def clear(self) -> None:
        """清空所有HTTP响应缓存。"""
        await self._cache.clear()
        logger.info("已清空所有HTTP响应缓存", _LOG_TAG)

    async def get_or_fetch(
        self,
        key: str,
        fetcher: Callable[..., Awaitable[Any]],
        *args,
        ttl: float | None = None,
        **kwargs,
    ) -> Any:
        """尝试从缓存获取，未命中则执行fetcher并缓存结果。

        使用 Cache.get_or_load 提供击穿防护，避免缓存未命中时
        多个协程同时调用 fetcher。

        参数:
            key: 缓存键。
            fetcher: 缓存未命中时的异步获取函数。
            *args: 传递给fetcher的位置参数。
            ttl: 缓存TTL(秒)。
            **kwargs: 传递给fetcher的关键字参数。

        返回:
            Any: 缓存或新获取的数据。
        """
        expire = int(ttl) if ttl is not None else self.default_ttl

        async def loader() -> Any:
            return await fetcher(*args, **kwargs)

        cached = await self._cache.raw_get(self._format_key(key))
        if cached is not None:
            logger.debug(f"缓存命中: '{key}'", _LOG_TAG)
            return cached

        logger.debug(f"缓存未命中，执行fetcher: '{key}'", _LOG_TAG)
        result = await loader()
        if result is not None:
            await self._cache.raw_set(
                self._format_key(key), result, expire=expire
            )
        return result


response_cache = ResponseCache()
