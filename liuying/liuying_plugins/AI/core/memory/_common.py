"""记忆系统公共常量与辅助函数

集中放置被多个记忆子模块共享的常量、提示词模板与无状态工具函数，
避免在子模块之间形成循环导入。
"""

import hashlib
import math
import re

from ...config import DEFAULT_PERSONA_FALLBACK

__all__ = ["MemoryEmbeddingUtils", "tokenize"]

_DEFAULT_PERSONA = DEFAULT_PERSONA_FALLBACK
"""默认人格名（数据列占位值，单源定义于插件 config）"""

_EMBEDDING_DIM = 64
"""默认嵌入维度"""

_RRF_K = 60
"""RRF融合参数"""

_REINFORCE_THRESHOLD = 3
"""巩固晋升阈值"""

_WORKING_EXPIRE_HOURS = 24
"""working层过期时间"""

_EPISODIC_EXPIRE_DAYS = 30
"""episodic层过期天数"""

_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z0-9]+")
"""词元提取模式：连续CJK段或连续字母数字段"""


def tokenize(text: str) -> list[str]:
    """零依赖中英文分词

    英文/数字按连续段整体作为词元（小写化），
    连续CJK段按 2-gram 展开（单字段保留单字），
    解决中文无空格时整句被当作单一词导致的嵌入退化。

    参数:
        text: 输入文本

    返回:
        list[str]: 词元列表
    """
    tokens: list[str] = []
    for match in _TOKEN_RE.finditer(text):
        seg = match.group()
        if "\u4e00" <= seg[0] <= "\u9fff":
            if len(seg) == 1:
                tokens.append(seg)
            else:
                tokens.extend(
                    seg[i : i + 2] for i in range(len(seg) - 1)
                )
        else:
            tokens.append(seg.lower())
    return tokens


class MemoryEmbeddingUtils:
    """记忆嵌入与实体提取工具集

    提供无外部依赖的哈希词袋嵌入与简单实体提取能力，
    作为记忆系统的默认降级方案。
    """

    @staticmethod
    def default_dim() -> int:
        """返回默认嵌入维度

        返回:
            int: 默认嵌入维度
        """
        return _EMBEDDING_DIM

    @staticmethod
    def hash_bow_embedding(
        text: str, dim: int = _EMBEDDING_DIM
    ) -> list[float]:
        """生成hash-bow嵌入向量

        使用blake2b哈希将词元映射到固定维度向量，再L2归一化。
        零外部依赖，适合作为默认嵌入方案。

        参数:
            text: 输入文本
            dim: 嵌入维度

        返回:
            list[float]: 归一化后的嵌入向量
        """
        vec = [0.0] * dim
        if not text:
            return vec
        for word in tokenize(text):
            h = hashlib.blake2b(word.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(h, "big") % dim
            vec[idx] += 1.0
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    @staticmethod
    def extract_entities_simple(text: str) -> list[dict]:
        """简单实体提取

        基于词元频率提取实体（无NLP依赖的简化方案），
        中文按 2-gram 统计，避免整句被当作单一实体。

        参数:
            text: 输入文本

        返回:
            list[dict]: 实体列表，每项含 name/type/weight
        """
        if not text:
            return []
        entities: list[dict] = []
        freq: dict[str, int] = {}
        for word in tokenize(text):
            if len(word) >= 2:
                freq[word] = freq.get(word, 0) + 1
        sorted_words = sorted(
            freq.items(), key=lambda x: x[1], reverse=True
        )[:5]
        for word, count in sorted_words:
            entities.append(
                {"name": word, "type": "keyword", "weight": float(count)}
            )
        return entities
