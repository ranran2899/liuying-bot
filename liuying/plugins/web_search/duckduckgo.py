"""DuckDuckGo 免配置搜索客户端

通过 DuckDuckGo HTML 接口实现免配置搜索，无需 API 密钥。
"""
import re
from urllib.parse import quote_plus

from liuying.utils.LLM.web_search.models import WebPageResult
from liuying.utils.LLM.web_search.registry import (
    SearchClientMeta,
    register_search_client,
)

from ._base import FreeSearchClientBase, strip_html_tags

_DUCKDUCKGO_URL = "https://html.duckduckgo.com/html/?q={query}"
"""DuckDuckGo HTML搜索URL"""

_DD_TITLE_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]*>(.*?)</a>',
    re.S,
)
"""DuckDuckGo标题正则"""

_DD_SNIPPET_RE = re.compile(
    r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
    re.S,
)
"""DuckDuckGo摘要正则"""

_DD_HREF_RE = re.compile(r'href="([^"]+)"', re.S)
"""DuckDuckGo链接正则"""


@register_search_client(
    SearchClientMeta(
        name="duckduckgo",
        display_name="DuckDuckGo 搜索",
        description="基于 DuckDuckGo HTML 接口的免配置搜索引擎",
        requires_api_key=False,
        free=True,
        keywords=("duckduckgo", "ddg"),
        priority=40,
    )
)
class DuckDuckGoClient(FreeSearchClientBase):
    """DuckDuckGo 搜索客户端"""

    async def _execute_search(
        self, query: str, count: int
    ) -> list[WebPageResult]:
        """执行 DuckDuckGo 搜索

        参数:
            query: 搜索关键词
            count: 返回结果数量

        返回:
            网页结果列表
        """
        url = _DUCKDUCKGO_URL.format(query=quote_plus(query))
        status, html = await self._http_get(url)
        if status != 200 or not html:
            return []

        return self._parse_ddg_html(html, count)

    def _parse_ddg_html(
        self, html: str, count: int
    ) -> list[WebPageResult]:
        """解析 DuckDuckGo 搜索结果 HTML

        参数:
            html: HTML 文本
            count: 最大返回数量

        返回:
            网页结果列表
        """
        title_matches = list(_DD_TITLE_RE.finditer(html))
        snippet_matches = list(_DD_SNIPPET_RE.finditer(html))
        total = min(len(title_matches), count)

        results: list[WebPageResult] = []
        for i in range(total):
            title = strip_html_tags(title_matches[i].group(1))
            href_match = _DD_HREF_RE.search(title_matches[i].group(0))
            url_str = href_match.group(1) if href_match else ""

            snippet = ""
            if i < len(snippet_matches):
                snippet = strip_html_tags(snippet_matches[i].group(1))

            if title:
                results.append(
                    self._build_web_page(
                        title=title,
                        url=url_str,
                        snippet=snippet,
                        source="duckduckgo",
                    )
                )
        return results


__all__ = ["DuckDuckGoClient"]
