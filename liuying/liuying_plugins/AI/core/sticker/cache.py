"""贴纸缓存

为贴纸查询结果提供内存缓存，
减少对数据库与LLM的重复调用。
"""

from typing import Any

from liuying.services.cache import CacheDict
from liuying.utils.log import logger

__all__ = ["StickerCache", "sticker_cache"]


_CACHE_NAME = "AI_STICKER_CACHE"
"""缓存字典名"""


_DEFAULT_TTL = 1800
"""默认缓存TTL（秒）"""


_DEFAULT_MAX_SIZE = 1024
"""默认缓存最大数量"""


class StickerCache:
    """贴纸访问缓存

    基于 CacheDict 缓存贴纸查询结果，
    支持 TTL 过期与 LRU 淘汰。
    """

    def __init__(self) -> None:
        """初始化贴纸缓存"""
        self._cache = CacheDict(
            _CACHE_NAME,
            expire=_DEFAULT_TTL,
            max_size=_DEFAULT_MAX_SIZE,
        )

    def _normalize_key(self, key: str) -> str:
        """规范化缓存键

        参数:
            key: 原始键

        返回:
            str: 规范化后的键
        """
        return (key or "").strip()

    def get(self, key: str) -> Any | None:
        """获取缓存值

        参数:
            key: 缓存键

        返回:
            Any | None: 缓存值，未命中返回None
        """
        norm_key = self._normalize_key(key)
        if not norm_key:
            return None
        return self._cache.get(norm_key)

    def set(self, key: str, value: Any) -> None:
        """写入缓存

        参数:
            key: 缓存键
            value: 缓存值
        """
        norm_key = self._normalize_key(key)
        if not norm_key or value is None:
            return
        self._cache.set(norm_key, value)

    def invalidate(self, key: str) -> None:
        """使指定键的缓存失效

        参数:
            key: 缓存键
        """
        norm_key = self._normalize_key(key)
        if not norm_key:
            return
        self._cache.pop(norm_key, None)
        logger.debug(
            f"贴纸缓存已失效: {norm_key}",
            command="AI",
        )

    def clear(self) -> None:
        """清空全部缓存"""
        self._cache.clear()


sticker_cache = StickerCache()
"""贴纸缓存单例"""
