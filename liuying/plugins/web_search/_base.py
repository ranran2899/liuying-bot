"""免配置搜索客户端基类

提供免配置搜索引擎客户端的公共功能，包括 HTTP GET 请求、
HTML 标签清理与日期解析。所有免配置客户端继承此类。
"""
import re

from httpx import HTTPStatusError

from liuying.services.LLM.web_search.base_client import BaseSearchClient
from liuying.services.LLM.web_search.exceptions import (
    NetworkError,
    RequestError,
)
from liuying.services.LLM.web_search.models import (
    SearchRequest,
    SearchResponse,
    WebPageResult,
)
from liuying.utils.http.http_utils import AsyncHttpx
from liuying.utils.log import logger

_REQUEST_TIMEOUT = 15.0
"""HTTP请求超时（秒）"""

_MAX_FREE_RESULTS = 10
"""免配置搜索最大结果数"""


def strip_html_tags(html: str) -> str:
    """去除HTML标签，提取纯文本

    参数:
        html: HTML文本

    返回:
        纯文本
    """
    if not html:
        return ""
    html = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", html, flags=re.I)
    html = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", html, flags=re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"&nbsp;", " ", html)
    html = re.sub(r"&amp;", "&", html)
    html = re.sub(r"&lt;", "<", html)
    html = re.sub(r"&gt;", ">", html)
    html = re.sub(r"&quot;", '"', html)
    html = re.sub(r"&#\d+;", " ", html)
    html = re.sub(r"\s+", " ", html)
    return html.strip()


class FreeSearchClientBase(BaseSearchClient):
    """免配置搜索客户端基类

    提供HTTP GET请求与HTML解析公共功能，子类只需实现
    _execute_search 方法返回 WebPageResult 列表。
    """

    async def search(self, request: SearchRequest) -> SearchResponse:
        """执行搜索

        参数:
            request: 搜索请求对象

        返回:
            搜索响应对象

        抛出:
            RequestError: 搜索请求失败
            NetworkError: 网络连接失败
        """
        request.validate()
        count = min(max(request.count, 1), _MAX_FREE_RESULTS)

        try:
            web_pages = await self._execute_search(
                request.query, count
            )
        except RequestError as e:
            logger.error(
                f"[{self._provider_name}] 请求失败: {e}"
            )
            return SearchResponse(
                query=request.query,
                web_pages=[],
                total_matches=0,
                provider=self._provider_name,
                raw_data={"error": "request_failed", "detail": str(e)},
            )
        except NetworkError as e:
            logger.error(
                f"[{self._provider_name}] 网络连接失败: {e}"
            )
            return SearchResponse(
                query=request.query,
                web_pages=[],
                total_matches=0,
                provider=self._provider_name,
                raw_data={"error": "network_error", "detail": str(e)},
            )
        except Exception as e:
            logger.error(
                f"[{self._provider_name}] 未知错误: {e}",
                exc_info=True,
            )
            return SearchResponse(
                query=request.query,
                web_pages=[],
                total_matches=0,
                provider=self._provider_name,
                raw_data={"error": "unknown", "detail": str(e)},
            )

        return SearchResponse(
            query=request.query,
            web_pages=web_pages,
            total_matches=len(web_pages),
            provider=self._provider_name,
            raw_data={"source": self._provider_name},
        )

    async def _execute_search(
        self, query: str, count: int
    ) -> list[WebPageResult]:
        """执行搜索（子类实现）

        参数:
            query: 搜索关键词
            count: 返回结果数量

        返回:
            网页结果列表

        抛出:
            RequestError: 搜索请求失败
            NetworkError: 网络连接失败
        """
        raise NotImplementedError

    async def _http_get(
        self,
        url: str,
        *,
        timeout: float = _REQUEST_TIMEOUT,
        follow_redirects: bool = True,
    ) -> tuple[int, str]:
        """HTTP GET 请求

        参数:
            url: 请求 URL
            timeout: 超时秒数
            follow_redirects: 是否跟随重定向

        返回:
            tuple[int, str]: (状态码, 响应文本)

        抛出:
            NetworkError: 网络连接失败
            RequestError: HTTP 错误
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        try:
            response = await AsyncHttpx.get(
                url,
                timeout=timeout,
                follow_redirects=follow_redirects,
                headers=headers,
            )
            return response.status_code, response.text
        except HTTPStatusError as e:
            status = e.response.status_code if e.response else 0
            raise RequestError(
                self._provider_name,
                f"HTTP {status} 错误",
                status_code=status,
            ) from e
        except Exception as e:
            raise NetworkError(self._provider_name, e) from e

    @staticmethod
    def _build_web_page(
        title: str,
        url: str,
        snippet: str,
        source: str,
        is_ad: bool = False,
        ad_source: str | None = None,
    ) -> WebPageResult:
        """构建网页结果对象

        参数:
            title: 标题
            url: URL
            snippet: 摘要
            source: 来源标识
            is_ad: 是否为广告结果
            ad_source: 广告来源

        返回:
            WebPageResult 实例
        """
        return WebPageResult(
            id="",
            title=title or "",
            url=url or "",
            snippet=snippet or "",
            site_name=source,
            is_ad=is_ad,
            ad_source=ad_source,
        )
