"""Bing HTTP 免配置搜索客户端

通过抓取 Bing 搜索结果页 HTML 实现免配置搜索，无需 API 密钥。
"""
import re
from urllib.parse import quote_plus

from liuying.utils.LLM.web_search.models import WebPageResult
from liuying.utils.LLM.web_search.registry import (
    SearchClientMeta,
    register_search_client,
)

from ._base import FreeSearchClientBase, strip_html_tags

_BING_SEARCH_URL = "https://www.bing.com/search?q={query}&count={count}"
"""Bing搜索URL模板"""

_BING_RESULT_RE = re.compile(
    r'<h2[^>]*><a[^>]*href="([^"]+)"[^>]*>(.*?)</a></h2>',
    re.S,
)
"""Bing搜索结果正则"""

_BING_EXCLUDE_DOMAINS = ("bing.com", "microsoft.com")
"""需排除的域名"""


@register_search_client(
    SearchClientMeta(
        name="bing_http",
        display_name="Bing HTTP 搜索",
        description="基于 Bing 搜索结果页 HTML 抓取的免配置搜索引擎",
        requires_api_key=False,
        free=True,
        keywords=("bing_http",),
        priority=10,
    )
)
class BingHttpClient(FreeSearchClientBase):
    """Bing HTTP 搜索客户端"""

    async def _execute_search(
        self, query: str, count: int
    ) -> list[WebPageResult]:
        """执行 Bing HTTP 搜索

        参数:
            query: 搜索关键词
            count: 返回结果数量

        返回:
            网页结果列表
        """
        url = _BING_SEARCH_URL.format(
            query=quote_plus(query), count=count
        )
        status, html = await self._http_get(url)
        if status != 200 or not html:
            return []

        return self._parse_bing_html(html, count)

    def _parse_bing_html(
        self, html: str, count: int
    ) -> list[WebPageResult]:
        """解析 Bing 搜索结果 HTML

        参数:
            html: HTML 文本
            count: 最大返回数量

        返回:
            网页结果列表
        """
        results: list[WebPageResult] = []
        seen_urls: set[str] = set()

        for match in _BING_RESULT_RE.finditer(html):
            url = match.group(1).strip()
            title = strip_html_tags(match.group(2))
            if not url or not title:
                continue
            if url.startswith("/"):
                url = "https://www.bing.com" + url
            if url in seen_urls:
                continue
            if any(domain in url for domain in _BING_EXCLUDE_DOMAINS):
                continue
            seen_urls.add(url)

            snippet = self._extract_bing_snippet(html, url)
            results.append(
                self._build_web_page(
                    title=title,
                    url=url,
                    snippet=snippet,
                    source="bing_http",
                )
            )
            if len(results) >= count:
                break
        return results

    @staticmethod
    def _extract_bing_snippet(html: str, url: str) -> str:
        """提取 Bing 搜索结果摘要

        参数:
            html: HTML 文本
            url: 结果 URL

        返回:
            摘要文本
        """
        idx = html.find(url)
        if idx < 0:
            return ""
        snippet_area = html[idx:idx + 1000]
        text = strip_html_tags(snippet_area)
        return text[:200]


__all__ = ["BingHttpClient"]
