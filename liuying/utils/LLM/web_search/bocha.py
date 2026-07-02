"""博查搜索客户端"""
from typing import Any

from liuying.utils.log import logger

from .base_client import BaseSearchClient
from .exceptions import RequestError
from .models import (
    ImageResult,
    SearchProvider,
    SearchRequest,
    SearchResponse,
    WebPageResult,
)
from .registry import SearchClientMeta, register_search_client

_BOCHA_DEFAULT_BASE_URL = "https://api.bochaai.com/v1"


@register_search_client(
    SearchClientMeta(
        name="bocha",
        display_name="博查搜索",
        description="博查 AI 搜索，支持网页与图片结果",
        default_base_url=_BOCHA_DEFAULT_BASE_URL,
        requires_api_key=True,
        keywords=("bocha", "bochaai"),
    )
)
class BochaClient(BaseSearchClient):
    """博查搜索API客户端"""

    def __init__(self, provider_name: str = "bocha"):
        """初始化博查搜索客户端

        参数:
            provider_name: 提供商名称，对应 LLM.PROVIDERS 中的 name
        """
        super().__init__(provider_name)

    async def search(self, request: SearchRequest) -> SearchResponse:
        """执行博查搜索

        Args:
            request: 搜索请求对象

        Returns:
            搜索响应对象
        """
        request.validate()

        api_key = self._get_api_key()
        base_url = self._get_base_url()

        url = f"{base_url}/web-search"
        headers = {"Authorization": f"Bearer {api_key}"}

        data = self._build_request_data(request)

        response_data = await self._request(url, headers, data)
        return self._parse_response(request.query, response_data)

    def _build_request_data(self, request: SearchRequest) -> dict[str, Any]:
        """构建请求数据

        Args:
            request: 搜索请求对象

        Returns:
            请求数据字典
        """
        data: dict[str, Any] = {
            "query": request.query,
            "count": request.count,
            "summary": request.summary,
            "freshness": request.freshness.value,
        }

        if request.search_filter:
            data.update(request.search_filter.to_bocha_params())

        return data

    def _parse_response(
        self, query: str, response_data: dict[str, Any]
    ) -> SearchResponse:
        """解析响应数据

        Args:
            query: 搜索关键词
            response_data: 响应数据

        Returns:
            搜索响应对象
        """
        code = response_data.get("code", -1)
        if code != 200:
            raise RequestError(
                "bocha",
                response_data.get("msg", "搜索请求失败"),
                status_code=code,
                response_data=response_data,
            )

        data = response_data.get("data", {})

        web_pages = [
            WebPageResult.from_bocha(item)
            for item in data.get("webPages", {}).get("value", [])
        ]

        images = [
            ImageResult.from_bocha(item)
            for item in data.get("images", {}).get("value", [])
        ]

        total_matches = data.get("webPages", {}).get("totalEstimatedMatches", 0)

        logger.debug(
            f"[博查搜索] 搜索完成: {query}, "
            f"网页 {len(web_pages)} 条, 图片 {len(images)} 条"
        )

        return SearchResponse(
            query=query,
            web_pages=web_pages,
            images=images,
            total_matches=total_matches,
            provider=SearchProvider.BOCHA,
            request_id=response_data.get("requestId"),
            raw_data=response_data,
        )
