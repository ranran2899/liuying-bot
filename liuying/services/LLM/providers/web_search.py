"""网络搜索 Provider，将搜索引擎封装为统一能力

通过注册表自动发现所有已注册的搜索客户端（含免配置客户端），
已配置的 provider 优先，失败时自动降级到免配置客户端。
"""
from typing import Any

from liuying.services.LLM.capabilities import Capability, WebSearchCapability
from liuying.services.LLM.configs import APIType, ProviderConfig
from liuying.services.LLM.provider import BaseProvider, register_provider
from liuying.services.LLM.web_search.base_client import BaseSearchClient
from liuying.services.LLM.web_search.exceptions import SearchError
from liuying.services.LLM.web_search.models import (
    FreshnessType,
    SearchFilter,
    SearchRequest,
    SearchResponse,
)
from liuying.services.LLM.web_search.registry import (
    get_free_search_clients,
    get_registered_search_clients,
    get_search_client_class,
)
from liuying.utils.log import logger


@register_provider(APIType.WEB_SEARCH)
class WebSearchProvider(BaseProvider, WebSearchCapability):
    """网络搜索 Provider

    通过注册表自动发现所有已注册的搜索客户端。
    需要API密钥的客户端由对应插件自行配置，免配置客户端作为降级兜底。
    """

    api_type = APIType.WEB_SEARCH
    default_capabilities = frozenset({Capability.WEB_SEARCH})

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._clients: dict[str, BaseSearchClient] = {}
        self._free_clients: dict[str, BaseSearchClient] = {}
        self._free_clients_loaded: bool = False
        self._default_provider: str = ""
        self._init_clients()

    def _init_clients(self) -> None:
        """从注册表初始化所有已注册的需要API密钥的客户端

        每个客户端自行管理配置（API密钥等），此处仅负责发现和实例化。
        第一个成功实例化的客户端作为默认 provider。
        """
        for name, meta in get_registered_search_clients().items():
            if meta.free:
                continue
            client_cls = get_search_client_class(name)
            if client_cls is None:
                continue
            try:
                client = client_cls(name)
                self._clients[name] = client
                if not self._default_provider:
                    self._default_provider = name
            except Exception as e:
                logger.debug(
                    f"搜索客户端 {name} 初始化失败（可能未配置密钥）: {e}",
                )

        if self._clients:
            logger.debug(
                f"已初始化 {len(self._clients)} 个搜索客户端: "
                f"{', '.join(self._clients.keys())}"
            )

    def _ensure_free_clients_loaded(self) -> None:
        """延迟加载免配置搜索客户端"""
        if self._free_clients_loaded:
            return
        self._free_clients_loaded = True
        for client_name, meta in get_free_search_clients():
            client_cls = get_search_client_class(client_name)
            if client_cls is None:
                continue
            self._free_clients[client_name] = client_cls(client_name)
            logger.debug(f"已加载免配置搜索客户端: {meta.display_name}")

    def capabilities(self) -> set[Capability]:
        declared = self._config.capabilities
        if declared:
            return {
                Capability(c) for c in declared if c in Capability.values()
            }
        return set(self.default_capabilities)

    def get_capability(self, capability: Capability) -> Any | None:
        if capability == Capability.WEB_SEARCH and capability in self.capabilities():
            return self
        return None

    async def search(
        self,
        query: str,
        engine: str | None = None,
        count: int = 10,
        options: dict[str, Any] | None = None,
    ) -> SearchResponse:
        """执行网络搜索，优先使用已配置引擎，失败时自动降级到免配置客户端。

        参数:
            query: 搜索关键词，不可为空。
            engine: 搜索引擎名称（如 "bing"），None 则使用默认引擎。
            count: 返回结果数量，范围 1-50，默认 10。
            options: 额外搜索选项字典，支持以下字段：
                - enable_free_fallback (bool): 主引擎失败时是否降级到免配置客户端，默认 True。
                - freshness (FreshnessType | str): 时间范围过滤，可选值
                  "noLimit"/"oneDay"/"oneWeek"/"oneMonth"/"oneYear"，默认 "noLimit"。
                - search_filter (SearchFilter | dict): 站点过滤条件，dict 形式接受
                  include_sites/exclude_sites/city 字段。
                - summary (bool): 是否返回结果摘要，默认 True（免配置降级时为 False）。
                - instruction (str): 搜索指令文本，仅支持指令的引擎生效。
                - chat_model (str): 聊天模型名称，用于支持总结的引擎。
                - extra (dict): 引擎特定专属参数，各引擎自行解析。

        返回:
            SearchResponse: 包含 web_pages/images/total_matches/provider 等字段的响应对象。

        异常:
            SearchError: 指定引擎不可用、或所有引擎（含降级）均失败时抛出。
        """
        options = options if options is not None else {}
        enable_fallback = options.get("enable_free_fallback", True)

        try:
            return await self._search_primary(query, engine, count, options)
        except SearchError as e:
            if not enable_fallback:
                raise
            self._ensure_free_clients_loaded()
            if not self._free_clients:
                raise
            logger.debug(
                f"主搜索引擎失败，降级到免配置客户端: {e}",
                command="LLM",
            )
            return await self._search_free_fallback(query, count, options)

    async def _search_primary(
        self,
        query: str,
        engine: str | None,
        count: int,
        options: dict[str, Any],
    ) -> SearchResponse:
        provider = engine or self._default_provider
        client = self._clients.get(provider)
        if client is None:
            available = ", ".join(self._clients.keys()) if self._clients else "无"
            raise SearchError(
                f"搜索引擎 '{provider}' 不可用，可用引擎: {available}",
                provider,
            )
        request = self._build_request(query, count, options)
        return await client.search(request)

    async def _search_free_fallback(
        self,
        query: str,
        count: int,
        options: dict[str, Any],
    ) -> SearchResponse:
        request = self._build_request(query, count, options, is_free=True)
        errors: list[str] = []
        for name, client in self._free_clients.items():
            try:
                return await client.search(request)
            except SearchError as e:
                errors.append(f"{name}: {e}")
                logger.debug(
                    f"免配置客户端 {name} 失败: {e}",
                    command="LLM",
                )
        raise SearchError(
            "所有搜索引擎均不可用，免配置降级失败: " + "; ".join(errors),
        )

    @staticmethod
    def _build_request(
        query: str,
        count: int,
        options: dict[str, Any],
        is_free: bool = False,
    ) -> SearchRequest:
        freshness = options.get("freshness", FreshnessType.NO_LIMIT)
        if isinstance(freshness, str):
            freshness = FreshnessType(freshness)
        search_filter = options.get("search_filter")
        if isinstance(search_filter, dict):
            search_filter = SearchFilter(**search_filter)

        return SearchRequest(
            query=query,
            count=count,
            summary=options.get("summary", not is_free),
            freshness=freshness,
            search_filter=search_filter,
            instruction=options.get("instruction"),
            chat_model=options.get("chat_model"),
            extra=options.get("extra", {}),
        )


__all__ = ["WebSearchProvider"]
