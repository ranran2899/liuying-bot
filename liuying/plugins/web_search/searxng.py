"""SearXNG 免配置搜索客户端

通过 SearXNG 公共实例实现免配置搜索，无需 API 密钥。
"""
import json
from urllib.parse import quote_plus

from liuying.utils.LLM.web_search.models import WebPageResult
from liuying.utils.LLM.web_search.registry import (
    SearchClientMeta,
    register_search_client,
)

from ._base import FreeSearchClientBase

_SEARXNG_INSTANCES: tuple[str, ...] = (
    "https://searx.be/search?q={query}&format=json",
    "https://search.sapti.me/search?q={query}&format=json",
)
"""SearXNG公共实例列表"""


@register_search_client(
    SearchClientMeta(
        name="searxng",
        display_name="SearXNG 搜索",
        description="基于 SearXNG 公共实例的免配置元搜索引擎",
        requires_api_key=False,
        free=True,
        keywords=("searxng", "searx"),
        priority=30,
    )
)
class SearXNGClient(FreeSearchClientBase):
    """SearXNG 搜索客户端"""

    async def _execute_search(
        self, query: str, count: int
    ) -> list[WebPageResult]:
        """执行 SearXNG 搜索

        依次尝试多个 SearXNG 公共实例，首个成功即返回。

        参数:
            query: 搜索关键词
            count: 返回结果数量

        返回:
            网页结果列表
        """
        for template in _SEARXNG_INSTANCES:
            url = template.format(query=quote_plus(query))
            try:
                status, text = await self._http_get(url)
            except Exception:
                continue
            if status != 200 or not text:
                continue

            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue

            raw_items = data.get("results", [])
            results: list[WebPageResult] = []
            for item in raw_items[:count]:
                results.append(
                    self._build_web_page(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        snippet=item.get("content", ""),
                        source="searxng",
                    )
                )
            if results:
                return results
        return []


__all__ = ["SearXNGClient"]
