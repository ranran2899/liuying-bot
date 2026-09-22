"""Bing HTTP 免配置搜索客户端

通过抓取 Bing 搜索结果页 HTML 实现免配置搜索，无需 API 密钥。
"""
import re
from urllib.parse import quote_plus

from liuying.services.LLM.web_search.models import WebPageResult
from liuying.services.LLM.web_search.registry import (
    SearchClientMeta,
    register_search_client,
)

from ._base import FreeSearchClientBase, strip_html_tags

# 配置常量
_BING_MAX_RESULTS = 10  # 最大结果数

_BING_SEARCH_URL = "https://cn.bing.com/search?q={query}"
"""Bing搜索URL模板"""

# 主搜索结果块正则：匹配 <li class="b_algo">...</li>
_BING_ALGO_BLOCK_RE = re.compile(
    r'<li[^>]*class="b_algo"[^>]*>(.*?)</li>',
    re.S,
)
"""Bing主搜索结果块正则"""

# 结果块内标题与URL正则
_BING_TITLE_RE = re.compile(
    r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    re.S,
)
"""Bing标题与URL正则"""

# 结果块内摘要正则：优先匹配 b_caption 内的 p 标签
_BING_SNIPPET_RE = re.compile(
    r'<div[^>]*class="b_caption"[^>]*>.*?<p[^>]*>(.*?)</p>',
    re.S,
)
"""Bing摘要正则（b_caption内）"""

# 兜底摘要正则：匹配任意 p 标签
_BING_SNIPPET_FALLBACK_RE = re.compile(
    r'<p[^>]*>(.*?)</p>',
    re.S,
)
"""Bing兜底摘要正则"""

# cite 标签 URL 正则（Bing 显示真实 URL 的位置）
_BING_CITE_RE = re.compile(
    r'<cite[^>]*>(.*?)</cite>',
    re.S,
)
"""Bing cite 标签 URL 正则"""

# 广告结果块正则
_BING_AD_BLOCK_RE = re.compile(
    r'<li[^>]*class="b_ad"[^>]*>(.*?)</li>',
    re.S,
)
"""Bing广告结果块正则"""

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
        priority=20,
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
            query=quote_plus(query)
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

        # 1. 解析主搜索结果（b_algo 块）
        for block_match in _BING_ALGO_BLOCK_RE.finditer(html):
            block = block_match.group(1)
            result = self._parse_result_block(block, seen_urls)
            if result is None:
                continue
            url, title, snippet = result
            seen_urls.add(url)
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
    def _parse_result_block(
        block: str, seen_urls: set[str]
    ) -> tuple[str, str, str] | None:
        """解析单个结果块，提取 URL、标题、摘要

        参数:
            block: 结果块 HTML
            seen_urls: 已见过的 URL 集合

        返回:
            (url, title, snippet) 或 None（无效结果）
        """
        title_match = _BING_TITLE_RE.search(block)
        if not title_match:
            return None

        url = title_match.group(1).strip()
        title = strip_html_tags(title_match.group(2))

        # 优先从 cite 标签提取真实 URL（Bing 显示的真实地址）
        cite_match = _BING_CITE_RE.search(block)
        if cite_match:
            cite_text = strip_html_tags(cite_match.group(1))
            if cite_text and not cite_text.startswith("http"):
                cite_text = "https://" + cite_text
            if cite_text and "bing.com" not in cite_text:
                url = cite_text

        if not url or not title:
            return None
        if url.startswith("/"):
            url = "https://www.bing.com" + url
        if url in seen_urls:
            return None
        if any(domain in url for domain in _BING_EXCLUDE_DOMAINS):
            return None

        # 提取摘要：优先 b_caption 内的 p 标签，兜底任意 p 标签
        snippet = ""
        snippet_match = _BING_SNIPPET_RE.search(block)
        if snippet_match:
            snippet = strip_html_tags(snippet_match.group(1))
        else:
            fallback_match = _BING_SNIPPET_FALLBACK_RE.search(block)
            if fallback_match:
                snippet = strip_html_tags(fallback_match.group(1))

        return url, title, snippet[:200].strip()


__all__ = ["BingHttpClient"]
