"""网络搜索 Provider，将搜索引擎封装为统一能力

通过注册表自动发现所有已注册的搜索客户端（含免配置客户端），
配置的 provider 优先，失败时自动降级到免配置客户端。
"""
from typing import Any

from liuying.utils.LLM.capabilities import Capability, WebSearchCapability
from liuying.utils.LLM.configs import APIType, ProviderConfig
from liuying.utils.LLM.provider import BaseProvider, register_provider
from liuying.utils.LLM.web_search.base_client import BaseSearchClient
from liuying.utils.LLM.web_search.config import get_search_config
from liuying.utils.LLM.web_search.exceptions import SearchError
from liuying.utils.LLM.web_search.models import (
    BaiduSearchMode,
    FreshnessType,
    SearchFilter,
    SearchRequest,
    SearchResponse,
)
from liuying.utils.LLM.web_search.registry import (
    get_free_search_clients,
    get_search_client_class,
)
from liuying.utils.LLM.web_search.tracker import search_tracker
from liuying.utils.log import logger


@register_provider(APIType.WEB_SEARCH)
class WebSearchProvider(BaseProvider, WebSearchCapability):
    """网络搜索 Provider

    支持 api_type 为 web_search 的配置，内部通过注册表自动发现
    所有已注册的搜索客户端。配置的 provider 优先，失败时自动降级
    到免配置客户端（Bing HTTP/Wikipedia/SearXNG/DuckDuckGo 等）。
    """

    api_type = APIType.WEB_SEARCH
    default_capabilities = frozenset({Capability.WEB_SEARCH})

    def __init__(self, config: ProviderConfig):
        """初始化网络搜索 Provider

        Args:
            config: 提供商配置
        """
        super().__init__(config)
        self._clients: dict[str, BaseSearchClient] = {}
        self._free_clients: dict[str, BaseSearchClient] = {}
        self._free_clients_loaded: bool = False
        self._init_clients()
        self._sync_daily_limit()

    def _init_clients(self) -> None:
        """根据搜索配置初始化已配置客户端

        遍历 LLM.PROVIDERS 中识别出的所有 web_search 提供商，
        通过注册表获取客户端类并实例化，key 为 provider 名称。
        """
        search_cfg = get_search_config()
        for name, provider_cfg in search_cfg.providers.items():
            client_cls = get_search_client_class(provider_cfg.client_type)
            if client_cls is None:
                logger.warning(
                    f"未注册的搜索客户端类型: {provider_cfg.client_type}，"
                    f"已跳过 provider: {name}"
                )
                continue
            self._clients[name] = client_cls(name)

    def _ensure_free_clients_loaded(self) -> None:
        """延迟加载免配置搜索客户端

        由于外部插件可能在 Provider 实例化之后才注册免配置客户端，
        此方法在第一次需要免配置降级时触发加载。
        """
        if self._free_clients_loaded:
            return
        self._free_clients_loaded = True
        search_cfg = get_search_config()
        if not search_cfg.free_clients_enabled:
            return
        for client_name, meta in get_free_search_clients():
            client_cls = get_search_client_class(client_name)
            if client_cls is None:
                continue
            self._free_clients[client_name] = client_cls(client_name)
            logger.debug(f"已加载免配置搜索客户端: {meta.display_name}")

    def _sync_daily_limit(self) -> None:
        """同步百度智能搜索生成每日免费额度到追踪器"""
        search_cfg = get_search_config()
        search_tracker.set_daily_limit(search_cfg.baidu_endpoint.daily_limit)

    def capabilities(self) -> set[Capability]:
        """获取支持的能力集合

        Returns:
            能力类型集合
        """
        declared = self._config.capabilities
        if declared:
            return {
                Capability(c) for c in declared if c in Capability.values()
            }
        return set(self.default_capabilities)

    def get_capability(self, capability: Capability) -> Any | None:
        """获取指定能力的实现

        Args:
            capability: 能力类型

        Returns:
            能力实现实例，不支持则返回 None
        """
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
        """执行网络搜索

        优先使用指定引擎或默认 provider，失败时自动降级到免配置客户端。

        Args:
            query: 搜索关键词
            engine: 搜索引擎名称，None 则使用默认
            count: 返回结果数量
            options: 额外选项，可包含 freshness、summary、search_filter、
                baidu_mode (web_search/chat/web_summary)、instruction、chat_model、
                enable_free_fallback (bool, 是否启用免配置降级，默认 True)

        Returns:
            搜索响应对象

        Raises:
            SearchError: 没有可用搜索引擎时抛出
        """
        options = options or {}
        enable_fallback = options.get("enable_free_fallback", True)

        try:
            return await self._search_primary(
                query, engine, count, options
            )
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
        """使用已配置的主搜索引擎搜索

        Args:
            query: 搜索关键词
            engine: 搜索引擎名称
            count: 返回结果数量
            options: 额外选项

        Returns:
            搜索响应对象

        Raises:
            SearchError: 没有可用搜索引擎时抛出
        """
        search_cfg = get_search_config()
        provider = engine or search_cfg.default_provider

        client = self._clients.get(provider)
        if client is None:
            available = ", ".join(self._clients.keys()) if self._clients else "无"
            raise SearchError(
                f"搜索引擎 '{provider}' 不可用，可用引擎: {available}",
                provider,
            )

        freshness = options.get("freshness", FreshnessType.NO_LIMIT)
        if isinstance(freshness, str):
            freshness = FreshnessType(freshness)
        search_filter = options.get("search_filter")
        if isinstance(search_filter, dict):
            search_filter = SearchFilter(**search_filter)

        baidu_mode = self._resolve_baidu_mode(options.get("baidu_mode"))

        if search_cfg.get_client_type(provider) == "baidu":
            await self._check_baidu_quota(baidu_mode)

        request = SearchRequest(
            query=query,
            count=count,
            summary=options.get("summary", True),
            freshness=freshness,
            search_filter=search_filter,
            baidu_mode=baidu_mode,
            instruction=options.get("instruction"),
            chat_model=options.get("chat_model"),
        )
        return await client.search(request)

    async def _search_free_fallback(
        self,
        query: str,
        count: int,
        options: dict[str, Any],
    ) -> SearchResponse:
        """使用免配置客户端降级搜索

        按优先级依次尝试免配置客户端，首个成功即返回。

        Args:
            query: 搜索关键词
            count: 返回结果数量
            options: 额外选项

        Returns:
            搜索响应对象

        Raises:
            SearchError: 所有免配置客户端均失败时抛出
        """
        freshness = options.get("freshness", FreshnessType.NO_LIMIT)
        if isinstance(freshness, str):
            freshness = FreshnessType(freshness)
        search_filter = options.get("search_filter")
        if isinstance(search_filter, dict):
            search_filter = SearchFilter(**search_filter)

        request = SearchRequest(
            query=query,
            count=count,
            summary=options.get("summary", False),
            freshness=freshness,
            search_filter=search_filter,
        )

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
    def _resolve_baidu_mode(raw: Any) -> BaiduSearchMode:
        """解析百度搜索模式

        参数:
            raw: 原始值，可为 None/str/BaiduSearchMode

        返回:
            BaiduSearchMode 枚举值
        """
        if raw is None:
            return BaiduSearchMode(
                get_search_config().baidu_endpoint.default_mode
            )
        if isinstance(raw, BaiduSearchMode):
            return raw
        if isinstance(raw, str):
            try:
                return BaiduSearchMode(raw)
            except ValueError:
                return BaiduSearchMode.WEB_SEARCH
        return BaiduSearchMode.WEB_SEARCH

    @staticmethod
    async def _check_baidu_quota(mode: BaiduSearchMode) -> None:
        """检查百度智能搜索生成剩余免费额度

        参数:
            mode: 百度搜索模式

        Raises:
            SearchError: 配额已用尽时抛出
        """
        if not await search_tracker.is_baidu_quota_available(mode.value):
            quota = await search_tracker.get_baidu_quota()
            raise SearchError(
                "百度智能搜索生成每日免费额度已用尽，"
                f"已用 {quota['used']}/{quota['daily_limit']}，"
                f"次日零点重置",
                "baidu",
            )


__all__ = ["WebSearchProvider"]
