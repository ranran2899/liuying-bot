"""记忆系统公共常量与辅助函数

集中放置被多个记忆子模块共享的常量、提示词模板与无状态工具函数，
避免在子模块之间形成循环导入。
"""

import hashlib
import math

_DEFAULT_PERSONA = "default"
"""默认人格名（未指定时回退）"""

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

_CONSOLIDATE_PROMPT = """请将以下对话记录摘要成一段简洁的记忆。

对话记录：
{history}

要求：
1. 提取关键信息和事件
2. 保留重要细节
3. 不超过100字
4. 只返回摘要文本"""


def _hash_bow_embedding(
    text: str, dim: int = _EMBEDDING_DIM
) -> list[float]:
    """生成hash-bow嵌入向量

    使用blake2b哈希将文本映射到固定维度向量，再L2归一化。
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
    words = text.split()
    for word in words:
        h = hashlib.blake2b(word.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(h, "big") % dim
        vec[idx] += 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


def _extract_entities_simple(text: str) -> list[dict]:
    """简单实体提取

    基于关键词频率提取实体（无NLP依赖的简化方案）。

    参数:
        text: 输入文本

    返回:
        list[dict]: 实体列表，每项含 name/type/weight
    """
    if not text:
        return []
    entities: list[dict] = []
    words = text.split()
    freq: dict[str, int] = {}
    for word in words:
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
