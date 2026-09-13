"""百度搜索客户端

支持百度千帆 AI 搜索三种模式：
- web_search: 百度搜索，仅返回网页搜索结果
- chat: 智能搜索生成，搜索后使用大模型总结(每日免费 100 次)
- web_summary: 智能搜索生成高性能版，整合搜索+大模型(每日免费 100 次)
"""
from typing import Any

from liuying.configs.config import Config
from liuying.services.LLM.web_search.base_client import BaseSearchClient
from liuying.services.LLM.web_search.exceptions import (
    APIKeyError,
    RequestError,
    SearchError,
)
from liuying.services.LLM.web_search.models import (
    FreshnessType,
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

from .models import BaiduSearchMode
from .tracker import baidu_quota_tracker

_MODULE = "BAIDU_SEARCH"


@register_search_client(
    SearchClientMeta(
        name="baidu",
        display_name="百度搜索",
        description="百度千帆 AI 搜索，支持 web_search/chat/web_summary 三种模式",
        default_base_url="https://qianfan.baidubce.com",
        requires_api_key=True,
        keywords=("baidu", "baidubce", "qianfan"),
    )
)
class BaiduClient(BaseSearchClient):
    """百度搜索API客户端"""

    def __init__(self, provider_name: str = "baidu"):
        super().__init__(provider_name)

    async def search(self, request: SearchRequest) -> SearchResponse:
        """执行百度搜索"""
        request.validate()

        mode = self._resolve_mode(request)
        await self._check_quota(mode)

        base_url = self._get_base_url()
        endpoint_path = self._get_endpoint_path(mode)
        url = f"{base_url.rstrip('/')}{endpoint_path}"

        api_key = self._get_api_key()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        data = self._build_request_data(request, mode)
        response_data = await self._request(url, headers, data)
        response = self._parse_response(request.query, mode, response_data)

        await search_tracker.record("baidu", mode.value)
        await baidu_quota_tracker.record(mode.value)
        return response

    def _get_api_key(self) -> str:
        api_key = Config.get_config(_MODULE, "API_KEY", "")
        if not api_key:
            raise APIKeyError("baidu")
        return api_key

    def _get_base_url(self) -> str:
        return Config.get_config(_MODULE, "BASE_URL", "https://qianfan.baidubce.com")

    def _get_endpoint_path(self, mode: BaiduSearchMode) -> str:
        match mode:
            case BaiduSearchMode.CHAT:
                return "/v2/ai_search/chat/completions"
            case BaiduSearchMode.WEB_SUMMARY:
                return "/v2/ai_search/web_summary"
            case _:
                return "/v2/ai_search/web_search"

    def _resolve_mode(self, request: SearchRequest) -> BaiduSearchMode:
        raw = request.extra.get("baidu_mode")
        if raw is None:
            default = Config.get_config(_MODULE, "DEFAULT_MODE", "web_search")
            return BaiduSearchMode(default)
        if isinstance(raw, BaiduSearchMode):
            return raw
        if isinstance(raw, str):
            try:
                return BaiduSearchMode(raw)
            except ValueError:
                return BaiduSearchMode.WEB_SEARCH
        return BaiduSearchMode.WEB_SEARCH

    async def _check_quota(self, mode: BaiduSearchMode) -> None:
        if not await baidu_quota_tracker.is_quota_available(mode.value):
            quota = await baidu_quota_tracker.get_quota()
            raise SearchError(
                "百度智能搜索生成每日免费额度已用尽，"
                f"已用 {quota['used']}/{quota['daily_limit']}，"
                f"次日零点重置",
                "baidu",
            )

    def _build_request_data(
        self, request: SearchRequest, mode: BaiduSearchMode
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "messages": [
                {"role": "user", "content": request.query},
            ],
            "search_source": "baidu_search_v2",
            "stream": False,
            "resource_type_filter": [
                {"type": "web", "top_k": request.count},
                {"type": "video", "top_k": 0},
                {"type": "image", "top_k": 0},
            ],
        }

        if request.freshness != FreshnessType.NO_LIMIT:
            data["search_recency_filter"] = self._convert_freshness(request.freshness)

        if request.search_filter:
            data.update(self._convert_filter(request.search_filter))

        if mode == BaiduSearchMode.CHAT:
            data["model"] = request.chat_model or Config.get_config(
                _MODULE, "CHAT_MODEL", "ernie-4.5-turbo-32k"
            )
            if request.instruction:
                data["instruction"] = request.instruction
        elif mode == BaiduSearchMode.WEB_SUMMARY:
            if request.instruction:
                data["instruction"] = request.instruction

        return data

    @staticmethod
    def _convert_freshness(freshness: FreshnessType) -> str:
        match freshness:
            case FreshnessType.ONE_DAY:
                return "week"
            case FreshnessType.ONE_WEEK:
                return "week"
            case FreshnessType.ONE_MONTH:
                return "month"
            case FreshnessType.ONE_YEAR:
                return "year"
            case _:
                return "year"

    @staticmethod
    def _convert_filter(search_filter: Any) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if search_filter.include_sites:
            params["match"] = {"site": search_filter.include_sites}
        if search_filter.city:
            params["geo"] = {"city": [search_filter.city]}
        return params

    def _parse_response(
        self,
        query: str,
        mode: BaiduSearchMode,
        response_data: dict[str, Any],
    ) -> SearchResponse:
        if error_msg := response_data.get("message"):
            code = response_data.get("code", -1)
            raise RequestError(
                "baidu",
                f"百度搜索请求失败: {error_msg}",
                status_code=code if isinstance(code, int) else None,
                response_data=response_data,
            )

        references = response_data.get("references", []) or []
        web_pages = [self._parse_reference(item) for item in references]

        summary_text = self._extract_summary(response_data)
        request_id = response_data.get("request_id") or response_data.get("requestId")

        logger.debug(
            f"[百度搜索] 模式={mode.value}, 查询={query}, "
            f"网页 {len(web_pages)} 条, 总结={'有' if summary_text else '无'}"
        )

        return SearchResponse(
            query=query,
            web_pages=web_pages,
            total_matches=len(web_pages),
            provider="baidu",
            request_id=request_id,
            raw_data=response_data,
            summary_text=summary_text,
        )

    @staticmethod
    def _parse_reference(data: dict[str, Any]) -> WebPageResult:
        return WebPageResult(
            id=str(data.get("id", "")),
            title=data.get("title", ""),
            url=data.get("url", ""),
            snippet=data.get("snippet") or data.get("content", ""),
            summary=data.get("content"),
            site_name=data.get("website") or data.get("web_anchor"),
            site_icon=data.get("icon"),
            published_date=WebPageResult._parse_iso_date(data.get("date"))
            or WebPageResult._parse_date(data.get("date")),
        )

    @staticmethod
    def _extract_summary(response_data: dict[str, Any]) -> str | None:
        choices = response_data.get("choices") or []
        if not choices:
            return None
        first_choice = choices[0] or {}
        message = first_choice.get("message") or first_choice.get("delta") or {}
        content = message.get("content")
        return content if content else None


__all__ = ["BaiduClient"]
