"""LLM配置管理模块 - 统一配置管理，消除配置冗余"""
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from liuying.configs.config import Config
from liuying.utils.log import logger


class APIType(StrEnum):
    """API类型枚举"""

    OPENAI = "openai"
    ZHIPU = "zhipu"
    GEMINI = "gemini"
    ARK = "ark"
    OPENROUTER = "openrouter"
    WEB_SEARCH = "web_search"

    @classmethod
    def values(cls) -> list[str]:
        """获取所有API类型值列表

        Returns:
            API类型字符串列表
        """
        return [m.value for m in cls]


@dataclass(slots=True)
class RequestDefaults:
    """请求默认参数配置"""

    temperature: float = 0.5
    max_tokens: int = 4096

    def to_dict(self) -> dict[str, Any]:
        """转换为字典

        Returns:
            默认参数字典
        """
        return {"temperature": self.temperature, "max_tokens": self.max_tokens}


@dataclass(slots=True)
class ModelConfig:
    """模型配置"""

    model_name: str
    api_type: str = ""
    extra_headers: dict[str, str] | None = None


@dataclass(slots=True)
class ProviderConfig:
    """提供商配置"""

    name: str
    api_key: str = ""
    api_base: str = ""
    api_type: str = ""
    models: list[ModelConfig] = field(default_factory=list)
    extra_headers: dict[str, str] | None = None
    capabilities: list[str] | None = None

    def get_model_config(self, model_name: str) -> ModelConfig | None:
        """获取指定模型配置

        Args:
            model_name: 模型名称

        Returns:
            模型配置，不存在则返回None
        """
        return next(
            (m for m in self.models if m.model_name == model_name),
            None,
        )

    def get_api_url(self, model_name: str | None = None) -> str:
        """获取API基础URL

        Args:
            model_name: 模型名称，某些提供商需要追加模型名

        Returns:
            API URL
        """
        if not self.api_base:
            return ""
        url = self.api_base.rstrip("/")
        if model_name and self.api_type == APIType.OPENAI:
            url = f"{url}/v1"
        return url

    @property
    def is_openai_compatible(self) -> bool:
        """判断是否为OpenAI兼容API

        Returns:
            是否兼容OpenAI格式
        """
        return self.api_type in (APIType.OPENAI, APIType.ARK, APIType.OPENROUTER)


@dataclass(slots=True)
class ClientSettings:
    """客户端设置"""

    timeout: int = 300
    max_retries: int = 3
    retry_delay: float = 1.0
    structured_retries: int = 2
    proxy: str = ""


@dataclass(slots=True)
class DebugLogConfig:
    """调试日志配置"""

    show_tools: bool = False
    show_schema: bool = False
    show_safety: bool = False


@dataclass(slots=True)
class LLMConfig:
    """LLM全局配置"""

    default_model_name: str = "GLM/glm-4-flash-250414"
    gemini_safety_threshold: str = "BLOCK_NONE"
    providers: list[ProviderConfig] = field(default_factory=list)
    client_settings: ClientSettings = field(default_factory=ClientSettings)
    debug_log: DebugLogConfig = field(default_factory=DebugLogConfig)
    request_defaults: RequestDefaults = field(default_factory=RequestDefaults)

    def get_provider(self, provider_name: str) -> ProviderConfig | None:
        """获取指定提供商配置

        Args:
            provider_name: 提供商名称

        Returns:
            提供商配置，不存在则返回None
        """
        name_lower = provider_name.lower()
        return next(
            (p for p in self.providers if p.name.lower() == name_lower),
            None,
        )

    def get_model_config(
        self, model_name: str
    ) -> tuple[ProviderConfig, ModelConfig] | None:
        """获取指定模型的完整配置

        Args:
            model_name: 模型名称

        Returns:
            (提供商配置, 模型配置) 元组，不存在则返回None
        """
        for provider in self.providers:
            if model_cfg := provider.get_model_config(model_name):
                return provider, model_cfg
        return None

    def get_default_provider(self) -> ProviderConfig | None:
        """获取默认提供商配置

        Returns:
            默认提供商配置
        """
        if not self.default_model_name:
            return None
        match self.default_model_name.split("/", 1):
            case [provider_name, _] if (provider := self.get_provider(provider_name)):
                return provider
            case [_] if self.providers:
                return self.providers[0]
            case _:
                return None

    def get_default_model(self) -> str | None:
        """获取默认模型名称

        Returns:
            默认模型名称
        """
        if not self.default_model_name:
            return None
        match self.default_model_name.split("/", 1):
            case [_, model] if model:
                return model
            case [name]:
                return name
            case _:
                return None

    def get_providers_by_type(self, api_type: str) -> list[ProviderConfig]:
        """按API类型获取提供商列表

        Args:
            api_type: API类型

        Returns:
            匹配的提供商配置列表
        """
        return [p for p in self.providers if p.api_type == api_type]


class LLMConfigManager:
    """LLM配置管理器"""

    _CONFIG_KEYS = (
        "DEFAULT_MODEL_NAME",
        "GEMINI_SAFETY_THRESHOLD",
        "PROVIDERS",
        "CLIENT_SETTINGS",
        "DEBUG_LOG",
    )

    def __init__(self):
        """初始化配置管理器"""
        self._config: LLMConfig | None = None

    @property
    def config(self) -> LLMConfig:
        """获取配置对象

        Returns:
            LLM配置对象
        """
        if self._config is None:
            self._load_config()
        return self._config

    def _load_config(self) -> None:
        """从配置文件加载配置"""
        raw: dict[str, Any] = {
            key: val
            for key in self._CONFIG_KEYS
            if (val := Config.get_config("LLM", key)) is not None
        }
        self._config = self._parse_config(raw)
        logger.info(f"已加载LLM配置，共 {len(self._config.providers)} 个提供商")

    def _parse_config(self, raw: dict[str, Any]) -> LLMConfig:
        """解析原始配置字典

        Args:
            raw: 原始配置字典

        Returns:
            LLMConfig对象
        """
        config = LLMConfig()

        match raw:
            case {"DEFAULT_MODEL_NAME": name}:
                config.default_model_name = name
            case _:
                pass

        match raw:
            case {"GEMINI_SAFETY_THRESHOLD": threshold}:
                config.gemini_safety_threshold = threshold
            case _:
                pass

        if "PROVIDERS" in raw:
            config.providers = self._parse_providers(raw["PROVIDERS"])
        if "CLIENT_SETTINGS" in raw:
            config.client_settings = self._parse_client_settings(
                raw["CLIENT_SETTINGS"]
            )
        if "DEBUG_LOG" in raw:
            config.debug_log = self._parse_debug_log(raw["DEBUG_LOG"])

        return config

    def _parse_providers(
        self, providers_raw: list[dict[str, Any]]
    ) -> list[ProviderConfig]:
        """解析提供商列表

        Args:
            providers_raw: 原始提供商列表

        Returns:
            提供商配置列表
        """
        return [
            ProviderConfig(
                name=p.get("name", ""),
                api_key=p.get("api_key", ""),
                api_base=p.get("api_base", ""),
                api_type=p.get("api_type", ""),
                extra_headers=p.get("extra_headers"),
                models=self._parse_models(
                    p.get("models", []), p.get("api_type", "")
                ),
                capabilities=p.get("capabilities"),
            )
            for p in providers_raw
        ]

    def _parse_models(
        self, models_raw: list[dict[str, Any]], api_type: str
    ) -> list[ModelConfig]:
        """解析模型列表

        Args:
            models_raw: 原始模型列表
            api_type: API类型

        Returns:
            模型配置列表
        """
        return [
            ModelConfig(
                model_name=m.get("model_name", ""),
                api_type=api_type,
                extra_headers=m.get("extra_headers"),
            )
            for m in models_raw
        ]

    def _parse_client_settings(self, raw: dict[str, Any]) -> ClientSettings:
        """解析客户端设置

        Args:
            raw: 原始客户端设置字典

        Returns:
            ClientSettings对象
        """
        return ClientSettings(
            timeout=raw.get("timeout", 300),
            max_retries=raw.get("max_retries", 3),
            retry_delay=raw.get("retry_delay", 1.0),
            structured_retries=raw.get("structured_retries", 2),
            proxy=raw.get("proxy", ""),
        )

    def _parse_debug_log(self, raw: dict[str, Any]) -> DebugLogConfig:
        """解析调试日志配置

        Args:
            raw: 原始调试日志配置字典

        Returns:
            DebugLogConfig对象
        """
        return DebugLogConfig(
            show_tools=raw.get("show_tools", False),
            show_schema=raw.get("show_schema", False),
            show_safety=raw.get("show_safety", False),
        )

    def reload(self) -> None:
        """重新加载配置"""
        self._config = None
        self._load_config()
        logger.info("LLM配置已重新加载")


llm_config_manager = LLMConfigManager()


def get_llm_config() -> LLMConfig:
    """获取LLM全局配置

    Returns:
        LLM配置对象
    """
    return llm_config_manager.config


def get_provider_config(provider_name: str) -> ProviderConfig | None:
    """获取指定提供商配置

    Args:
        provider_name: 提供商名称

    Returns:
        提供商配置，不存在则返回None
    """
    return llm_config_manager.config.get_provider(provider_name)


def get_model_config(
    model_name: str,
) -> tuple[ProviderConfig, ModelConfig] | None:
    """获取指定模型的完整配置

    Args:
        model_name: 模型名称

    Returns:
        (提供商配置, 模型配置) 元组，不存在则返回None
    """
    return llm_config_manager.config.get_model_config(model_name)


def get_all_providers() -> list[ProviderConfig]:
    """获取所有已配置的提供商

    Returns:
        提供商配置列表
    """
    return llm_config_manager.config.providers


def get_supported_api_types() -> list[str]:
    """获取所有支持的API类型

    Returns:
        API类型列表
    """
    return list({p.api_type for p in llm_config_manager.config.providers if p.api_type})


__all__ = [
    "APIType",
    "ClientSettings",
    "DebugLogConfig",
    "LLMConfig",
    "LLMConfigManager",
    "ModelConfig",
    "ProviderConfig",
    "RequestDefaults",
    "get_all_providers",
    "get_llm_config",
    "get_model_config",
    "get_provider_config",
    "get_supported_api_types",
    "llm_config_manager",
]
