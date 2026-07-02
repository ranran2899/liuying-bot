"""百度搜索客户端

支持百度千帆 AI 搜索三种模式：
- web_search: 百度搜索，仅返回网页搜索结果
- chat: 智能搜索生成，搜索后使用大模型总结(每日免费 100 次)
- web_summary: 智能搜索生成高性能版，整合搜索+大模型(每日免费 100 次)
"""
from typing import Any

from liuying.utils.log import logger

from .base_client import BaseSearchClient
from .exceptions import RequestError
from .models import (
    BaiduSearchMode,
    FreshnessType,
    SearchProvider,
    SearchRequest,
    SearchResponse,
    WebPageResult,
)
from .registry import SearchClientMeta, register_search_client
from .tracker import search_tracker

_BAIDU_DEFAULT_BASE_URL = "https://qianfan.baidubce.com"


@register_search_client(
    SearchClientMeta(
        name="baidu",
        display_name="百度搜索",
        description="百度千帆 AI 搜索，支持 web_search/chat/web_summary 三种模式",
        default_base_url=_BAIDU_DEFAULT_BASE_URL,
        requires_api_key=True,
        keywords=("baidu", "baidubce", "qianfan"),
    )
)
class BaiduClient(BaseSearchClient):
    """百度搜索API客户端"""

    def __init__(self, provider_name: str = "baidu"):
        """初始化百度搜索客户端

        参数:
            provider_name: 提供商名称，对应 LLM.PROVIDERS 中的 name
        """
        super().__init__(provider_name)

    async def search(self, request: SearchRequest) -> SearchResponse:
        """执行百度搜索

        根据 request.baidu_mode 选择对应的千帆 AI 搜索端点，
        统一记录调用次数到 search_tracker。

        Args:
            request: 搜索请求对象

        Returns:
            搜索响应对象
        """
        request.validate()

        mode = request.baidu_mode
        endpoint_path = self._get_endpoint_path(mode)
        base_url = self._get_base_url()
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
        return response

    def _get_endpoint_path(self, mode: BaiduSearchMode) -> str:
        """获取指定模式对应的端点路径

        Args:
            mode: 百度搜索模式

        Returns:
            端点路径字符串
        """
        return self._config.baidu_endpoint.get_endpoint(mode.value)

    def _build_request_data(
        self, request: SearchRequest, mode: BaiduSearchMode
    ) -> dict[str, Any]:
        """构建请求数据

        不同模式的请求体结构统一采用千帆 v2 接口的 messages 格式，
        差异在于 chat/web_summary 模式需要传入 model 字段。

        Args:
            request: 搜索请求对象
            mode: 百度搜索模式

        Returns:
            请求数据字典
        """
        endpoint_cfg = self._config.baidu_endpoint
        data: dict[str, Any] = {
            "messages": [
                {"role": "user", "content": request.query},
            ],
            "search_source": endpoint_cfg.search_source,
            "stream": False,
            "resource_type_filter": [
                {"type": "web", "top_k": request.count},
                {"type": "video", "top_k": 0},
                {"type": "image", "top_k": 0},
            ],
        }

        if request.freshness != FreshnessType.NO_LIMIT:
            data["search_recency_filter"] = self._convert_freshness(
                request.freshness
            )

        if request.search_filter:
            filter_params = request.search_filter.to_baidu_params()
            data.update(filter_params)

        if mode == BaiduSearchMode.CHAT:
            data["model"] = request.chat_model or endpoint_cfg.chat_model
            if request.instruction:
                data["instruction"] = request.instruction
        elif mode == BaiduSearchMode.WEB_SUMMARY:
            if request.instruction:
                data["instruction"] = request.instruction

        return data

    @staticmethod
    def _convert_freshness(freshness: FreshnessType) -> str:
        """将内部 FreshnessType 转换为百度 API 时间过滤参数

        Args:
            freshness: 时间范围类型

        Returns:
            百度 API 接受的时间过滤字符串
        """
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

    def _parse_response(
        self,
        query: str,
        mode: BaiduSearchMode,
        response_data: dict[str, Any],
    ) -> SearchResponse:
        """解析响应数据

        Args:
            query: 搜索关键词
            mode: 百度搜索模式
            response_data: 响应数据

        Returns:
            搜索响应对象
        """
        if error_msg := response_data.get("message"):
            code = response_data.get("code", -1)
            raise RequestError(
                "baidu",
                f"百度搜索请求失败: {error_msg}",
                status_code=code if isinstance(code, int) else None,
                response_data=response_data,
            )

        references = response_data.get("references", []) or []
        web_pages = [WebPageResult.from_baidu_v2(item) for item in references]

        summary_text = self._extract_summary(response_data)
        request_id = response_data.get("request_id") or response_data.get(
            "requestId"
        )

        logger.debug(
            f"[百度搜索] 模式={mode.value}, 查询={query}, "
            f"网页 {len(web_pages)} 条, 总结={'有' if summary_text else '无'}"
        )

        return SearchResponse(
            query=query,
            web_pages=web_pages,
            total_matches=len(web_pages),
            provider=SearchProvider.BAIDU,
            request_id=request_id,
            raw_data=response_data,
            summary_text=summary_text,
            baidu_mode=mode,
        )

    @staticmethod
    def _extract_summary(response_data: dict[str, Any]) -> str | None:
        """从响应中提取大模型总结文本

        Args:
            response_data: 响应数据

        Returns:
            总结文本，无总结时返回 None
        """
        choices = response_data.get("choices") or []
        if not choices:
            return None
        first_choice = choices[0] or {}
        message = first_choice.get("message") or first_choice.get("delta") or {}
        content = message.get("content")
        return content if content else None
