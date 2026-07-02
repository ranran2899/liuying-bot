"""搜索结果排序器

基于相关性、时效性、权威性对搜索结果进行综合排序。
"""

from datetime import datetime
import re
from urllib.parse import urlparse

_AUTHORITATIVE_DOMAINS: frozenset[str] = frozenset({
    "wikipedia.org",
    "zh.wikipedia.org",
    "github.com",
    "stackoverflow.com",
    "arxiv.org",
    "gov.cn",
    "edu.cn",
    "mozilla.org",
    "python.org",
})
"""权威域名集合"""

_FRESHNESS_DAYS = 30
"""时效性判定天数"""

_DATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})"),
    re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})"),
    re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日"),
)
"""日期正则元组"""

_DEFAULT_WEIGHTS: dict[str, float] = {
    "relevance": 0.5,
    "freshness": 0.25,
    "authority": 0.25,
}
"""默认评分权重"""


class SearchRanker:
    """搜索结果排序器

    基于相关性、时效性、权威性多维评分排序。
    """

    def __init__(
        self,
        weights: dict[str, float] | None = None,
    ) -> None:
        """初始化排序器

        参数:
            weights: 评分权重，None时用默认值
        """
        self._weights = weights or dict(_DEFAULT_WEIGHTS)

    def rank(
        self, results: list[dict], query: str
    ) -> list[dict]:
        """对搜索结果排序

        综合相关性、时效性、权威性评分，降序排列。

        参数:
            results: 搜索结果列表
            query: 原始查询文本

        返回:
            list[dict]: 排序后的结果列表（每个结果附带score字段）
        """
        if not results:
            return []
        query_terms = self._extract_terms(query)
        now = datetime.now()

        scored: list[tuple[float, dict]] = []
        for item in results:
            relevance = self._score_relevance(
                item, query_terms
            )
            freshness = self._score_freshness(item, now)
            authority = self._score_authority(item)
            total = (
                self._weights["relevance"] * relevance
                + self._weights["freshness"] * freshness
                + self._weights["authority"] * authority
            )
            item_with_score = dict(item)
            item_with_score["score"] = round(total, 4)
            scored.append((total, item_with_score))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored]

    def _extract_terms(self, query: str) -> list[str]:
        """提取查询词项

        参数:
            query: 查询文本

        返回:
            list[str]: 词项列表
        """
        if not query:
            return []
        cleaned = re.sub(r"[^\w\u4e00-\u9fa5]+", " ", query)
        terms = [
            t.strip().lower()
            for t in cleaned.split()
            if t.strip()
        ]
        return terms

    def _score_relevance(
        self, item: dict, query_terms: list[str]
    ) -> float:
        """计算相关性评分

        参数:
            item: 搜索结果项
            query_terms: 查询词项列表

        返回:
            float: 相关性评分（0.0-1.0）
        """
        if not query_terms:
            return 0.5
        title = (item.get("title", "") or "").lower()
        snippet = (item.get("snippet", "") or "").lower()
        combined = f"{title} {snippet}"
        hits = sum(
            1 for term in query_terms if term in combined
        )
        return min(hits / len(query_terms), 1.0)

    def _score_freshness(
        self, item: dict, now: datetime
    ) -> float:
        """计算时效性评分

        参数:
            item: 搜索结果项
            now: 当前时间

        返回:
            float: 时效性评分（0.0-1.0）
        """
        text = (
            f"{item.get('title', '')} "
            f"{item.get('snippet', '')}"
        )
        for pattern in _DATE_PATTERNS:
            match = pattern.search(text)
            if match:
                try:
                    date_str = (
                        f"{match.group(1)}-"
                        f"{int(match.group(2)):02d}-"
                        f"{int(match.group(3)):02d}"
                    )
                    pub_date = datetime.fromisoformat(date_str)
                    delta = (now - pub_date).days
                    if delta < 0:
                        return 1.0
                    if delta <= _FRESHNESS_DAYS:
                        return (
                            1.0
                            - delta / _FRESHNESS_DAYS * 0.5
                        )
                    return max(
                        0.1,
                        1.0 - delta / 365.0,
                    )
                except (ValueError, OSError):
                    continue
        return 0.3

    def _score_authority(self, item: dict) -> float:
        """计算权威性评分

        参数:
            item: 搜索结果项

        返回:
            float: 权威性评分（0.0-1.0）
        """
        url = item.get("url", "") or ""
        if not url:
            return 0.2
        try:
            domain = urlparse(url).netloc.lower()
            domain = domain.lstrip("www.")
        except Exception:
            return 0.2
        for auth in _AUTHORITATIVE_DOMAINS:
            if domain == auth or domain.endswith(f".{auth}"):
                return 1.0
        if domain.endswith(".gov") or domain.endswith(".edu"):
            return 0.9
        if domain.endswith(".org"):
            return 0.7
        if domain.endswith(".com"):
            return 0.4
        return 0.3


search_ranker = SearchRanker()
"""搜索结果排序器单例"""
