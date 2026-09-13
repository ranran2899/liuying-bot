"""博查搜索客户端"""
from typing import Any

from liuying.configs.config import Config
from liuying.services.LLM.web_search.base_client import BaseSearchClient
from liuying.services.LLM.web_search.exceptions import APIKeyError, RequestError
from liuying.services.LLM.web_search.models import (
    ImageResult,
    SearchRequest,
    SearchResponse,
    WebPageResult,
)
from liuying.services.LLM.web_search.registry import (
    SearchClientMeta,
    register_search_client,
)
from liuying.services.LLM.web_search.tracker import search_tracker
from liuying.utils.log import logger

_MODULE = "BOCHA_SEARCH"


@register_search_client(
    SearchClientMeta(
        name="bocha",
        display_name="博查搜索",
        description="博查 AI 搜索，支持网页与图片结果",
        default_base_url="https://api.bochaai.com/v1",
        requires_api_key=True,
        keywords=("bocha", "bochaai"),
    )
)
class BochaClient(BaseSearchClient):
    """博查搜索API客户端"""

    def __init__(self, provider_name: str = "bocha"):
        super().__init__(provider_name)

    async def search(self, request: SearchRequest) -> SearchResponse:
        request.validate()

        api_key = self._get_api_key()
        base_url = self._get_base_url()
        url = f"{base_url}/web-search"
        headers = {"Authorization": f"Bearer {api_key}"}

        data = self._build_request_data(request)
        response_data = await self._request(url, headers, data)
        response = self._parse_response(request.query, response_data)
        await search_tracker.record("bocha")
        return response

    def _get_api_key(self) -> str:
        api_key = Config.get_config(_MODULE, "API_KEY", "")
        if not api_key:
            raise APIKeyError("bocha")
        return api_key

    def _get_base_url(self) -> str:
        return Config.get_config(_MODULE, "BASE_URL", "https://api.bochaai.com/v1")

    def _build_request_data(self, request: SearchRequest) -> dict[str, Any]:
        data: dict[str, Any] = {
            "query": request.query,
            "count": request.count,
            "summary": request.summary,
            "freshness": request.freshness.value,
        }
        if request.search_filter:
            data.update(self._convert_filter(request.search_filter))
        return data

    @staticmethod
    def _convert_filter(search_filter: Any) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if search_filter.include_sites:
            params["include"] = "|".join(search_filter.include_sites)
        if search_filter.exclude_sites:
            params["exclude"] = "|".join(search_filter.exclude_sites)
        return params

    def _parse_response(
        self, query: str, response_data: dict[str, Any]
    ) -> SearchResponse:
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
            WebPageResult(
                id=item.get("id", ""),
                title=item.get("name", ""),
                url=item.get("url", ""),
                snippet=item.get("snippet", ""),
                summary=item.get("summary"),
                site_name=item.get("siteName"),
                site_icon=item.get("siteIcon"),
                published_date=WebPageResult._parse_iso_date(item.get("datePublished")),
                crawled_date=WebPageResult._parse_iso_date(item.get("dateLastCrawled")),
                language=item.get("language"),
                display_url=item.get("displayUrl"),
            )
            for item in data.get("webPages", {}).get("value", [])
        ]

        images = [
            ImageResult(
                id=item.get("imageId", ""),
                content_url=item.get("contentUrl", ""),
                host_page_url=item.get("hostPageUrl"),
                name=item.get("name"),
                width=item.get("width"),
                height=item.get("height"),
                thumbnail_url=item.get("thumbnailUrl"),
            )
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
            provider="bocha",
            request_id=response_data.get("requestId"),
            raw_data=response_data,
        )


__all__ = ["BochaClient"]
