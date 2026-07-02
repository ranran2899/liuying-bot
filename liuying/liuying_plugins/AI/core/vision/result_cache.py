"""图片理解结果缓存

基于图片URL哈希作为key，缓存图片理解结果，
避免对同一图片的重复LLM调用。
"""

import hashlib

from liuying.services.cache import CacheDict
from liuying.utils.log import logger

from ...config import get_config

__all__ = ["ImageResultCache", "image_result_cache"]


_CACHE_NAME = "AI_VISION_RESULT_CACHE"
"""缓存字典名"""


_DEFAULT_TTL = 3600
"""默认缓存TTL（秒）"""


_DEFAULT_MAX_SIZE = 512
"""默认缓存最大数量"""


class ImageResultCache:
    """图片理解结果缓存

    使用 CacheDict 存储图片URL哈希到理解结果的映射，
    支持TTL过期与LRU淘汰。
    """

    def __init__(self) -> None:
        """初始化图片理解结果缓存"""
        self._cache = CacheDict(
            _CACHE_NAME,
            expire=_DEFAULT_TTL,
            max_size=_DEFAULT_MAX_SIZE,
        )

    def _is_enabled(self) -> bool:
        """检查缓存是否启用

        返回:
            bool: 是否启用
        """
        return bool(get_config("IMAGE_RESULT_CACHE_ENABLED", True))

    def _make_key(self, url: str) -> str:
        """根据URL生成缓存键

        参数:
            url: 图片URL

        返回:
            str: URL的SHA256哈希前缀
        """
        return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]

    def get(self, url: str) -> str | None:
        """获取缓存的理解结果

        参数:
            url: 图片URL

        返回:
            str | None: 理解结果文本，未命中返回None
        """
        if not self._is_enabled() or not url:
            return None
        key = self._make_key(url)
        result = self._cache.get(key)
        if result is None:
            return None
        if not isinstance(result, str):
            logger.debug(
                "图片结果缓存值类型异常，已忽略",
                command="AI",
            )
            return None
        return result

    def set(self, url: str, result: str) -> None:
        """写入理解结果缓存

        参数:
            url: 图片URL
            result: 理解结果文本
        """
        if not self._is_enabled() or not url or not result:
            return
        key = self._make_key(url)
        self._cache.set(key, result)

    def invalidate(self, url: str) -> None:
        """使指定URL的缓存失效

        参数:
            url: 图片URL
        """
        if not url:
            return
        key = self._make_key(url)
        self._cache.pop(key, None)

    def clear(self) -> None:
        """清空全部缓存"""
        self._cache.clear()


image_result_cache = ImageResultCache()
"""图片理解结果缓存单例"""
