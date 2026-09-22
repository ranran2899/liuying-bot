"""搜索结果排名

对记忆/知识检索结果按置信度、稳定性、显著性、时间敏感性、
群组范围、用户匹配度等维度综合排序，提升记忆召回质量。

本模块为纯函数逻辑，不发起网络/LLM 调用。
"""

import re
import time
from typing import Any

from ...models.memory_item import MemoryTier

__all__ = ["SearchRanker", "search_ranker"]


_TIME_HINT_RE = re.compile(
    r"(今天|昨天|前天|刚才|最近|上次|之前|前几天|本周|"
    r"上周|本月|去年|\d+天前|\d+个月前)"
)
"""时间提示词模式"""

_LATEST_TOKENS: tuple[str, ...] = (
    "最新", "现在", "当前", "今天", "刚刚", "最近",
)
"""最新感关键词"""

_AMBIGUOUS_TOKENS: tuple[str, ...] = (
    "是谁", "哪个", "哪部", "什么番", "这个", "上次",
)
"""模糊查询关键词"""

_CONFIDENCE_WEIGHT = 0.28
"""置信度权重"""

_STABILITY_WEIGHT = 0.22
"""稳定性权重"""

_SALIENCE_WEIGHT = 0.18
"""显著性权重"""

_REINFORCEMENT_WEIGHT = 0.018
"""巩固次数权重"""

_ACCESS_WEIGHT = 0.012
"""访问次数权重"""

_SAME_GROUP_BONUS = 0.18
"""同群加分"""

_CROSS_GROUP_PENALTY = -0.32
"""跨群扣分"""

_CROSS_GROUP_ALLOWED_PENALTY = -0.14
"""跨群允许时扣分"""

_NO_GROUP_PENALTY = -0.04
"""无群组扣分"""

_SAME_USER_BONUS = 0.10
"""同用户加分"""

_SEMANTIC_TIER_BONUS = 0.16
"""semantic层加分"""

_BACKGROUND_TIER_PENALTY = -0.18
"""background层扣分"""

_SUPERSEDED_PENALTY = -0.42
"""被取代扣分"""

_EXPIRED_PENALTY = -0.50
"""过期扣分"""

_LAST_ACCESS_BONUS = 0.08
"""最近访问加分"""


class SearchRanker:
    """搜索结果排名器

    封装记忆检索结果的综合排序逻辑。所有方法均为静态方法，
    可直接通过类名调用。

    排序维度：
    - 置信度（confidence）：越高越靠前
    - 稳定性（stability）：越高越靠前
    - 显著性（salience）：越高越靠前
    - 巩固次数（reinforcement_count）：越多越靠前
    - 访问次数（access_count）：越多越靠前
    - 群组范围匹配：同群加分、跨群扣分
    - 用户匹配：同用户加分
    - 记忆层级：semantic加分、background扣分
    - 时间敏感性：高敏感度记忆随时间衰减
    - 被取代/过期：大幅扣分
    """

    @staticmethod
    def _safe_float(
        value: Any, default: float = 0.0
    ) -> float:
        """安全转换为float

        参数:
            value: 待转换值
            default: 默认值

        返回:
            float: 转换结果
        """
        if isinstance(value, int | float) and not isinstance(
            value, bool
        ):
            return float(value)
        return default

    @staticmethod
    def query_looks_latest(query: str) -> bool:
        """判断查询是否在寻找最新信息

        参数:
            query: 查询文本

        返回:
            bool: 是否在寻找最新信息
        """
        lowered = str(query or "").strip().lower()
        return any(
            token in lowered for token in _LATEST_TOKENS
        )

    @staticmethod
    def query_looks_ambiguous(query: str) -> bool:
        """判断查询是否模糊

        参数:
            query: 查询文本

        返回:
            bool: 是否模糊查询
        """
        normalized = str(query or "").strip()
        if not normalized:
            return False
        if len(normalized) <= 4:
            return True
        return any(
            token in normalized
            for token in _AMBIGUOUS_TOKENS
        )

    @staticmethod
    def _time_hint_score(
        query: str,
        created_at: float,
        expire_at: float,
    ) -> float:
        """计算时间提示词得分

        参数:
            query: 查询文本
            created_at: 创建时间戳
            expire_at: 过期时间戳

        返回:
            float: 时间提示词得分
        """
        if not query or not _TIME_HINT_RE.search(
            str(query or "")
        ):
            return 0.0
        now = time.time()
        if expire_at and expire_at <= now:
            return -0.35
        age_hours = max(
            0.0,
            (now - float(created_at or 0.0)) / 3600.0,
        )
        return max(0.0, 0.28 - min(age_hours, 168.0) / 600.0)

    @staticmethod
    def _group_scope_delta(
        candidate_group_id: str,
        requested_group_id: str,
    ) -> float:
        """计算群组范围匹配得分

        参数:
            candidate_group_id: 候选记忆的群组ID
            requested_group_id: 请求的群组ID

        返回:
            float: 群组范围得分
        """
        if not requested_group_id:
            return 0.0
        if candidate_group_id == requested_group_id:
            return _SAME_GROUP_BONUS
        if not candidate_group_id:
            return _NO_GROUP_PENALTY
        return _CROSS_GROUP_PENALTY

    @staticmethod
    def rank_memory_payload(
        payload: dict[str, Any],
        *,
        query: str,
        base_score: float,
        requested_group_id: str = "",
        requested_user_id: str = "",
    ) -> float:
        """对记忆payload综合排序

        参数:
            payload: 记忆数据字典
            query: 查询文本
            base_score: 基础得分（如向量相似度）
            requested_group_id: 请求的群组ID
            requested_user_id: 请求的用户ID

        返回:
            float: 综合得分（越高越靠前）
        """
        confidence = SearchRanker._safe_float(
            payload.get("confidence", 0.5), 0.5
        )
        stability = SearchRanker._safe_float(
            payload.get("stability", 0.4), 0.4
        )
        salience = SearchRanker._safe_float(
            payload.get("salience", 0.4), 0.4
        )
        reinforcement_count = float(
            int(payload.get("reinforcement_count", 0) or 0)
        )
        access_count = float(
            int(payload.get("access_count", 0) or 0)
        )
        superseded_by = str(
            payload.get("superseded_by", "") or ""
        )
        expire_at = SearchRanker._safe_float(
            payload.get("expire_time", 0.0), 0.0
        )
        created_at = SearchRanker._safe_float(
            payload.get("create_time", 0.0), 0.0
        )
        last_accessed = SearchRanker._safe_float(
            payload.get("last_access_time", 0.0), 0.0
        )
        tier = str(
            payload.get("tier", "") or ""
        ).strip().lower()
        payload_group_id = str(
            payload.get("group_id", "") or ""
        )
        payload_user_id = str(
            payload.get("user_id", "") or ""
        )

        score = float(base_score)
        score += confidence * _CONFIDENCE_WEIGHT
        score += stability * _STABILITY_WEIGHT
        score += salience * _SALIENCE_WEIGHT
        score += min(reinforcement_count, 8.0) * _REINFORCEMENT_WEIGHT
        score += min(access_count, 12.0) * _ACCESS_WEIGHT
        score += SearchRanker._group_scope_delta(
            payload_group_id, requested_group_id
        )
        if (
            requested_user_id
            and payload_user_id
            and payload_user_id == requested_user_id
        ):
            score += _SAME_USER_BONUS
        if tier == MemoryTier.SEMANTIC:
            score += _SEMANTIC_TIER_BONUS
        elif tier == MemoryTier.BACKGROUND:
            score += _BACKGROUND_TIER_PENALTY
        if superseded_by:
            score += _SUPERSEDED_PENALTY
        if expire_at and expire_at <= time.time():
            score += _EXPIRED_PENALTY
        if last_accessed:
            age_days = (time.time() - last_accessed) / 86400.0
            score += max(
                0.0,
                _LAST_ACCESS_BONUS - age_days * 0.01,
            )
        score += SearchRanker._time_hint_score(
            query, created_at, expire_at
        )
        if (
            SearchRanker.query_looks_latest(query)
            and tier == MemoryTier.BACKGROUND
        ):
            score -= 0.10
        return round(score, 6)


search_ranker = SearchRanker()
"""搜索排名器单例"""
