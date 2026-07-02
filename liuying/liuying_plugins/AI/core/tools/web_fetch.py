"""网页抓取服务

抓取指定URL的网页内容，提取正文文本。
HTTP 请求复用本体 AsyncHttpx，统一连接池与超时管理。
"""

from dataclasses import dataclass
import re
from urllib.parse import urlparse

from httpx import HTTPStatusError

from liuying.utils.http.http_utils import AsyncHttpx

_MAX_CONTENT_LENGTH = 8000
"""网页内容最大长度"""


_REQUEST_TIMEOUT = 15.0
"""HTTP请求超时（秒）"""


@dataclass(slots=True)
class WebPageContent:
    """网页内容

    Attributes:
        url: URL
        title: 标题
        text: 正文文本
        success: 是否成功
        error: 错误信息
        status_code: HTTP状态码
        content_length: 内容长度
    """

    url: str = ""
    title: str = ""
    text: str = ""
    success: bool = False
    error: str = ""
    status_code: int = 0
    content_length: int = 0


class WebFetcher:
    """网页抓取工具集

    封装URL校验、HTML清洗、标题提取、HTTP请求等工具方法。
    """

    @staticmethod
    def _is_valid_url(url: str) -> bool:
        """验证URL有效性

        参数:
            url: URL字符串

        返回:
            bool: 是否有效
        """
        if not url:
            return False
        try:
            parsed = urlparse(url)
            return bool(
                parsed.scheme in ("http", "https") and parsed.netloc
            )
        except Exception:
            return False

    @staticmethod
    def _strip_html_tags(html: str) -> str:
        """去除HTML标签，提取纯文本

        参数:
            html: HTML文本

        返回:
            str: 纯文本
        """
        if not html:
            return ""
        html = re.sub(
            r"<script[^>]*>[\s\S]*?</script>", "", html, flags=re.I
        )
        html = re.sub(
            r"<style[^>]*>[\s\S]*?</style>", "", html, flags=re.I
        )
        html = re.sub(r"<[^>]+>", " ", html)
        html = re.sub(r"&nbsp;", " ", html)
        html = re.sub(r"&amp;", "&", html)
        html = re.sub(r"&lt;", "<", html)
        html = re.sub(r"&gt;", ">", html)
        html = re.sub(r"&quot;", '"', html)
        html = re.sub(r"&#\d+;", " ", html)
        html = re.sub(r"\s+", " ", html)
        return html.strip()

    @staticmethod
    def _extract_title(html: str) -> str:
        """从HTML提取标题

        参数:
            html: HTML文本

        返回:
            str: 标题
        """
        match = re.search(
            r"<title[^>]*>([^<]*)</title>", html, re.I
        )
        if match:
            return match.group(1).strip()
        return ""

    @staticmethod
    async def _http_get(
        url: str,
        *,
        timeout: float = _REQUEST_TIMEOUT,
    ) -> tuple[int, str, str]:
        """HTTP GET请求

        复用本体 AsyncHttpx，统一连接池与超时管理。

        参数:
            url: URL
            timeout: 超时秒数

        返回:
            tuple[int, str, str]: (状态码, 内容, 错误信息)
        """
        try:
            response = await AsyncHttpx.get(
                url,
                timeout=timeout,
                follow_redirects=True,
            )
            return response.status_code, response.text, ""
        except HTTPStatusError as e:
            status = e.response.status_code if e.response else 0
            return status, "", str(e)
        except Exception as e:
            return 0, "", str(e)


class WebFetchService:
    """网页抓取服务

    抓取指定URL的网页内容，提取正文文本。
    """

    async def fetch(
        self,
        url: str,
        *,
        max_length: int = _MAX_CONTENT_LENGTH,
    ) -> WebPageContent:
        """抓取网页内容

        参数:
            url: URL
            max_length: 最大内容长度

        返回:
            WebPageContent: 网页内容
        """
        if not _is_valid_url(url):
            return WebPageContent(url=url, error="无效的URL")

        status, html, error = await _http_get(url)
        if error:
            return WebPageContent(url=url, error=error)
        if status != 200:
            return WebPageContent(
                url=url,
                status_code=status,
                error=f"HTTP {status}",
            )

        title = _extract_title(html)
        text = _strip_html_tags(html)
        if len(text) > max_length:
            text = text[:max_length] + "..."

        return WebPageContent(
            url=url,
            title=title,
            text=text,
            success=True,
            status_code=status,
            content_length=len(text),
        )

    async def fetch_as_context(
        self,
        url: str,
        *,
        max_length: int = 4000,
    ) -> str:
        """抓取网页并格式化为AI上下文文本

        参数:
            url: URL
            max_length: 最大内容长度

        返回:
            str: 格式化的上下文文本
        """
        page = await self.fetch(url, max_length=max_length)
        if not page.success:
            return f"抓取失败: {page.error}"

        parts: list[str] = []
        if page.title:
            parts.append(f"标题: {page.title}")
        parts.append(f"URL: {url}")
        if page.text:
            parts.append(f"内容:\n{page.text}")
        return "\n".join(parts)


web_fetch = WebFetchService()
"""网页抓取服务单例"""


# 向后兼容别名：保持模块级函数引用以兼容旧调用方
_is_valid_url = WebFetcher._is_valid_url
_strip_html_tags = WebFetcher._strip_html_tags
_extract_title = WebFetcher._extract_title
_http_get = WebFetcher._http_get
