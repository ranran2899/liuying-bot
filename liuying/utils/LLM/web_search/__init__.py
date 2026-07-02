"""网络搜索工具包

提供标准化的搜索客户端注册机制，允许其他开发者将自定义搜索实现
注册到 LLM 模块。通过 register_search_client 装饰器自动注册。

使用方式:
    from liuying.utils.LLM.web_search import (
        BaseSearchClient,
        SearchClientMeta,
        register_search_client,
    )

    @register_search_client(SearchClientMeta(
        name="my_engine",
        display_name="我的搜索引擎",
        description="自定义搜索实现",
        keywords=("my_engine",),
    ))
    class MyClient(BaseSearchClient):
        async def search(self, request: SearchRequest) -> SearchResponse:
            ...
    """
from .baidu import BaiduClient
from .base_client import BaseSearchClient
from .bocha import BochaClient
from .config import (
    BaiduEndpointConfig,
    SearchConfig,
    SearchProviderConfig,
    get_search_config,
)
from .exceptions import (
    APIKeyError,
    NetworkError,
    RateLimitError,
    RequestError,
    SearchError,
    ValidationError,
)
from .models import (
    BaiduSearchMode,
    FreshnessType,
    ImageResult,
    ResourceType,
    SearchFilter,
    SearchProvider,
    SearchRequest,
    SearchResponse,
    WebPageResult,
)
from .registry import (
    SearchClientMeta,
    detect_client_type,
    get_free_search_clients,
    get_registered_search_clients,
    get_search_client_class,
    get_search_client_meta,
    register_search_client,
)
from .tracker import SearchUsageTracker, search_tracker

__all__ = [
    "APIKeyError",
    "BaiduClient",
    "BaiduEndpointConfig",
    "BaiduSearchMode",
    "BaseSearchClient",
    "BochaClient",
    "FreshnessType",
    "ImageResult",
    "NetworkError",
    "RateLimitError",
    "RequestError",
    "ResourceType",
    "SearchClientMeta",
    "SearchConfig",
    "SearchError",
    "SearchFilter",
    "SearchProvider",
    "SearchProviderConfig",
    "SearchRequest",
    "SearchResponse",
    "SearchUsageTracker",
    "ValidationError",
    "WebPageResult",
    "detect_client_type",
    "get_free_search_clients",
    "get_registered_search_clients",
    "get_search_client_class",
    "get_search_client_meta",
    "get_search_config",
    "register_search_client",
    "search_tracker",
]
