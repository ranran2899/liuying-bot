"""Wikipedia 免配置搜索客户端

通过 Wikipedia API 实现免配置搜索，无需 API 密钥。
"""
import json
from urllib.parse import quote_plus

from liuying.utils.LLM.web_search.models import WebPageResult
from liuying.utils.LLM.web_search.registry import (
    SearchClientMeta,
    register_search_client,
)

from ._base import FreeSearchClientBase, strip_html_tags

_WIKIPEDIA_API = (
    "https://zh.wikipedia.org/w/api.php"
    "?action=query&list=search&srsearch={query}"
    "&srlimit={count}&format=json&utf8=1"
)
"""Wikipedia搜索API模板"""


@register_search_client(
    SearchClientMeta(
        name="wikipedia",
        display_name="Wikipedia 搜索",
        description="基于 Wikipedia API 的免配置搜索引擎，适合百科类查询",
        requires_api_key=False,
        free=True,
        keywords=("wikipedia",),
        priority=20,
    )
)
class WikipediaClient(FreeSearchClientBase):
    """Wikipedia 搜索客户端"""

    async def _execute_search(
        self, query: str, count: int
    ) -> list[WebPageResult]:
        """执行 Wikipedia 搜索

        参数:
            query: 搜索关键词
            count: 返回结果数量

        返回:
            网页结果列表
        """
        url = _WIKIPEDIA_API.format(
            query=quote_plus(query), count=count
        )
        status, text = await self._http_get(url)
        if status != 200 or not text:
            return []

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []

        items = data.get("query", {}).get("search", [])
        results: list[WebPageResult] = []
        for item in items:
            title = item.get("title", "")
            page_id = item.get("pageid", "")
            snippet = strip_html_tags(item.get("snippet", ""))
            page_url = (
                f"https://zh.wikipedia.org/?curid={page_id}"
                if page_id
                else ""
            )
            results.append(
                self._build_web_page(
                    title=title,
                    url=page_url,
                    snippet=snippet,
                    source="wikipedia",
                )
            )
        return results


__all__ = ["WikipediaClient"]
