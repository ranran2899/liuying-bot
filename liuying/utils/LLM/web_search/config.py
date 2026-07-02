"""网络搜索配置管理

所有搜索提供商统一从 LLM.PROVIDERS 中读取 api_type 为 web_search 的条目，
不再读取旧的 WEB_SEARCH__* 配置。客户端类型通过注册表自动推断，
免配置客户端（free=True）由全局开关控制。
"""
from dataclasses import dataclass, field

from liuying.utils.LLM.configs import get_all_providers
from liuying.utils.log import logger

from .registry import detect_client_type, get_search_client_meta

# 百度默认端点与运行参数
_BAIDU_DEFAULT_WEB_SEARCH_URL = "/v2/ai_search/web_search"
_BAIDU_DEFAULT_CHAT_SEARCH_URL = "/v2/ai_search/chat/completions"
_BAIDU_DEFAULT_WEB_SUMMARY_URL = "/v2/ai_search/web_summary"
_BAIDU_DEFAULT_MODE = "web_search"
_BAIDU_DEFAULT_CHAT_MODEL = "ernie-4.5-turbo-32k"
_BAIDU_DEFAULT_SEARCH_SOURCE = "baidu_search_v2"
_BAIDU_DEFAULT_DAILY_LIMIT = 100


@dataclass(slots=True)
class SearchProviderConfig:
    """搜索提供商配置

    Attributes:
        api_key: API密钥
        base_url: 基础URL
        client_type: 客户端类型标识符（如 baidu/bocha/bing_http）
        timeout: 超时时间
        max_retries: 最大重试次数
    """

    api_key: str = ""
    base_url: str = ""
    client_type: str = ""
    timeout: int = 30
    max_retries: int = 3


@dataclass(slots=True)
class BaiduEndpointConfig:
    """百度搜索端点配置

    封装百度三种搜索模式的端点路径与运行参数。
    """

    web_search_url: str = _BAIDU_DEFAULT_WEB_SEARCH_URL
    chat_search_url: str = _BAIDU_DEFAULT_CHAT_SEARCH_URL
    web_summary_url: str = _BAIDU_DEFAULT_WEB_SUMMARY_URL
    default_mode: str = _BAIDU_DEFAULT_MODE
    chat_model: str = _BAIDU_DEFAULT_CHAT_MODEL
    search_source: str = _BAIDU_DEFAULT_SEARCH_SOURCE
    daily_limit: int = _BAIDU_DEFAULT_DAILY_LIMIT

    def get_endpoint(self, mode: str) -> str:
        """根据搜索模式获取端点路径

        参数:
            mode: 搜索模式 (web_search/chat/web_summary)

        返回:
            端点路径字符串
        """
        match mode:
            case "chat":
                return self.chat_search_url
            case "web_summary":
                return self.web_summary_url
            case _:
                return self.web_search_url


@dataclass(slots=True)
class SearchConfig:
    """搜索全局配置

    Attributes:
        default_provider: 默认提供商名称
        providers: 需要API密钥的提供商配置字典
        baidu_endpoint: 百度端点配置
        free_clients_enabled: 是否启用免配置搜索客户端
    """

    default_provider: str = ""
    providers: dict[str, SearchProviderConfig] = field(default_factory=dict)
    baidu_endpoint: BaiduEndpointConfig = field(
        default_factory=BaiduEndpointConfig
    )
    free_clients_enabled: bool = True

    def get_api_key(self, provider: str) -> str:
        """获取指定提供商的API密钥

        Args:
            provider: 提供商名称

        Returns:
            API密钥
        """
        if provider_cfg := self.providers.get(provider):
            return provider_cfg.api_key
        return ""

    def get_base_url(self, provider: str) -> str:
        """获取指定提供商的基础URL

        Args:
            provider: 提供商名称

        Returns:
            基础URL
        """
        if provider_cfg := self.providers.get(provider):
            return provider_cfg.base_url
        return ""

    def get_timeout(self, provider: str) -> int:
        """获取指定提供商的超时时间

        Args:
            provider: 提供商名称

        Returns:
            超时时间（秒）
        """
        if provider_cfg := self.providers.get(provider):
            return provider_cfg.timeout
        return 30

    def get_max_retries(self, provider: str) -> int:
        """获取指定提供商的最大重试次数

        Args:
            provider: 提供商名称

        Returns:
            最大重试次数
        """
        if provider_cfg := self.providers.get(provider):
            return provider_cfg.max_retries
        return 3

    def get_client_type(self, provider: str) -> str:
        """获取指定提供商的客户端类型

        Args:
            provider: 提供商名称

        Returns:
            客户端类型标识符
        """
        if provider_cfg := self.providers.get(provider):
            return provider_cfg.client_type
        return ""


class SearchConfigManager:
    """搜索配置管理器"""

    def __init__(self):
        """初始化配置管理器"""
        self._config: SearchConfig | None = None

    @property
    def config(self) -> SearchConfig:
        """获取配置对象"""
        if self._config is None:
            self._load_config()
        return self._config

    def _load_config(self) -> None:
        """从 LLM.PROVIDERS 加载 web_search 类型配置"""
        providers = self._load_from_llm_providers()
        if not providers:
            self._config = SearchConfig()
            logger.warning(
                "未在 LLM.PROVIDERS 中配置有效的 web_search 类型提供商，"
                "将仅使用免配置搜索客户端（如有）"
            )
            return

        first_name = next(iter(providers))
        self._config = SearchConfig(
            default_provider=first_name,
            providers=providers,
        )
        logger.debug(
            f"已从 LLM.PROVIDERS 加载搜索配置，"
            f"共 {len(providers)} 个提供商"
        )

    def _load_from_llm_providers(self) -> dict[str, SearchProviderConfig]:
        """从 LLM 配置中加载 web_search 类型的搜索提供商

        通过注册表 detect_client_type 自动推断客户端类型，
        provider 名称直接使用 LLM.PROVIDERS 中的 name（小写）。

        Returns:
            搜索提供商配置字典
        """
        providers: dict[str, SearchProviderConfig] = {}
        for provider_cfg in get_all_providers():
            if provider_cfg.api_type != "web_search":
                continue
            if not provider_cfg.api_key:
                continue
            name = provider_cfg.name.lower()
            client_type = detect_client_type(
                provider_cfg.name, provider_cfg.api_base
            )
            if not client_type:
                logger.warning(
                    f"无法识别搜索提供商类型，已跳过: {provider_cfg.name}"
                )
                continue
            meta = get_search_client_meta(client_type)
            default_base = meta.default_base_url if meta else ""
            providers[name] = SearchProviderConfig(
                api_key=provider_cfg.api_key,
                base_url=provider_cfg.api_base or default_base,
                client_type=client_type,
            )
        return providers

    def reload(self) -> None:
        """重新加载配置"""
        self._config = None
        self._load_config()


_search_config_manager = SearchConfigManager()


def get_search_config() -> SearchConfig:
    """获取搜索全局配置

    Returns:
        搜索配置对象
    """
    return _search_config_manager.config


__all__ = [
    "BaiduEndpointConfig",
    "SearchConfig",
    "SearchConfigManager",
    "SearchProviderConfig",
    "get_search_config",
]
