"""向量嵌入服务

提供文本嵌入向量的统一访问：优先调用 LLM 真实嵌入，
失败或未配置时降级到 hash-bow 哈希嵌入。
嵌入结果通过缓存服务缓存，避免重复计算。
"""

import hashlib

from liuying.services.cache import Cache
from liuying.utils.log import logger

from ...config import get_config
from ..llm import llm_helper
from ._common import _hash_bow_embedding

_EMBEDDING_CACHE_TYPE = "AI_EMBEDDING"
"""嵌入缓存类型"""

_EMBEDDING_CACHE_EXPIRE = 3600
"""嵌入缓存过期时间（秒）"""


class EmbeddingService:
    """向量嵌入服务

    优先调用 LLM 真实嵌入（llm_helper.embedding），
    失败或未配置时降级到 hash-bow 哈希嵌入。
    通过缓存服务缓存嵌入结果，相同文本不重复计算。
    """

    def __init__(self) -> None:
        """初始化嵌入服务"""
        self._cache: Cache[list] = Cache(
            _EMBEDDING_CACHE_TYPE, result_type=list
        )

    def _cache_key(self, text: str) -> str:
        """生成嵌入缓存键

        参数:
            text: 输入文本

        返回:
            str: 基于文本哈希的缓存键
        """
        digest = hashlib.blake2b(
            text.encode("utf-8"), digest_size=16
        ).hexdigest()
        return f"emb:{digest}"

    def _is_llm_enabled(self) -> bool:
        """判断是否启用 LLM 真实嵌入

        返回:
            bool: 配置了嵌入 provider 时返回 True
        """
        return bool(get_config("EMBEDDING_PROVIDER", None))

    async def _compute(self, text: str) -> list[float]:
        """计算嵌入向量（LLM 优先，降级 hash-bow）

        参数:
            text: 输入文本

        返回:
            list[float]: 嵌入向量
        """
        if self._is_llm_enabled():
            try:
                return await llm_helper.embedding(text)
            except Exception as e:
                logger.warning(
                    f"LLM嵌入失败，降级到hash-bow: {e}",
                    command="AI",
                    e=e,
                )
        return _hash_bow_embedding(text)

    async def embed(self, text: str) -> list[float]:
        """生成文本嵌入向量

        优先返回缓存结果；未命中时优先调用 LLM 真实嵌入，
        失败时降级到 hash-bow 哈希嵌入，并将结果写入缓存。

        参数:
            text: 输入文本

        返回:
            list[float]: 嵌入向量
        """
        if not text or not text.strip():
            return _hash_bow_embedding(text)
        cache_key = self._cache_key(text)
        try:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                return cached
        except Exception as e:
            logger.debug(
                f"读取嵌入缓存失败: {e}", command="AI", e=e
            )
        vector = await self._compute(text)
        try:
            await self._cache.set(
                cache_key, vector, expire=_EMBEDDING_CACHE_EXPIRE
            )
        except Exception as e:
            logger.debug(
                f"写入嵌入缓存失败: {e}", command="AI", e=e
            )
        return vector


embedding_service = EmbeddingService()
"""嵌入服务单例"""
