"""LLM管理器 - 统一对外接口，所有LLM功能通过此模块访问"""
from typing import Any

from liuying.utils.log import logger

from .capabilities import Capability
from .configs import LLMConfig, ModelConfig, ProviderConfig, llm_config_manager
from .provider import BaseProvider, get_provider_class
from .utils import APIError


class LLMManager:
    """LLM管理器，统一管理所有LLM相关功能

    对外唯一入口，所有配置查询、Provider获取、能力调用均通过此类。
    """

    def __init__(self):
        """初始化LLM管理器"""
        self._providers: dict[str, BaseProvider] = {}
        self._init_providers()

    def _init_providers(self) -> None:
        """根据配置自动注册并初始化所有 Provider"""
        from . import providers  # noqa: F401 触发 Provider 注册

        config = self.config
        for provider_cfg in config.providers:
            if not provider_cfg.api_type:
                continue
            provider_cls = get_provider_class(provider_cfg.api_type)
            if provider_cls is None:
                logger.warning(
                    f"未找到 api_type '{provider_cfg.api_type}' 对应的 Provider 实现，"
                    f"已跳过 '{provider_cfg.name}'"
                )
                continue
            self._providers[provider_cfg.name.lower()] = provider_cls(provider_cfg)

        logger.info(
            f"已初始化LLM管理器，共 {len(self._providers)} 个提供商: "
            f"{', '.join(self._providers.keys())}"
        )

    @property
    def config(self) -> LLMConfig:
        """获取LLM全局配置

        Returns:
            LLM配置对象
        """
        return llm_config_manager.config

    def get_model_config(
        self, model_name: str
    ) -> tuple[ProviderConfig, ModelConfig] | None:
        """获取指定模型的完整配置

        Args:
            model_name: 模型名称

        Returns:
            (提供商配置, 模型配置) 元组，不存在则返回None
        """
        return self.config.get_model_config(model_name)

    def get_provider_config(self, provider_name: str) -> ProviderConfig | None:
        """获取指定提供商配置

        Args:
            provider_name: 提供商名称

        Returns:
            提供商配置，不存在则返回None
        """
        return self.config.get_provider(provider_name)

    def get_provider(self, provider_name: str) -> BaseProvider | None:
        """获取指定 Provider 实例

        Args:
            provider_name: 提供商名称

        Returns:
            Provider 实例，不存在则返回 None
        """
        return self._providers.get(provider_name.lower())

    def get_default_provider(self) -> BaseProvider | None:
        """获取默认 Provider 实例

        Returns:
            默认 Provider 实例，不存在则返回 None
        """
        if not self.config.default_model_name:
            return next((p for p in self._providers.values()), None)

        match self.config.default_model_name.split("/", 1):
            case [provider_name, _]:
                if provider := self._providers.get(provider_name.lower()):
                    return provider
            case _:
                pass

        return next((p for p in self._providers.values()), None)

    def get_all_providers(self) -> list[ProviderConfig]:
        """获取所有已配置的提供商

        Returns:
            提供商配置列表
        """
        return self.config.providers

    def get_available_models(self) -> list[ModelConfig]:
        """获取所有可用模型列表

        Returns:
            模型配置列表
        """
        models: list[ModelConfig] = []
        for provider in self.config.providers:
            models.extend(provider.models)
        return models

    def get_available_model_names(self) -> list[str]:
        """获取所有可用模型名称列表

        Returns:
            模型名称列表
        """
        return [m.model_name for m in self.get_available_models()]

    def get_capability(
        self, provider_name: str, capability: Capability
    ) -> Any | None:
        """获取指定 Provider 的某个能力实现

        Args:
            provider_name: 提供商名称
            capability: 能力类型

        Returns:
            能力实现实例，不存在或不支持则返回 None
        """
        if provider := self._providers.get(provider_name.lower()):
            return provider.get_capability(capability)
        return None

    def get_capabilities(self, provider_name: str) -> dict[str, Any]:
        """获取指定 Provider 支持的所有能力实现

        Args:
            provider_name: 提供商名称

        Returns:
            能力名称到实例的映射字典
        """
        if provider := self._providers.get(provider_name.lower()):
            return {
                cap.value: provider.get_capability(cap)
                for cap in provider.capabilities()
            }
        return {}

    async def call_capability(
        self,
        provider_name: str,
        capability: Capability,
        method: str,
        *args,
        **kwargs,
    ) -> Any:
        """统一调用指定 Provider 的某个能力方法

        Args:
            provider_name: 提供商名称
            capability: 能力类型
            method: 能力方法名
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            方法返回值

        Raises:
            APIError: Provider 不存在或能力不支持
        """
        cap = self.get_capability(provider_name, capability)
        if cap is None:
            raise APIError(
                f"Provider '{provider_name}' 不存在或不支持能力 '{capability.value}'",
                "CAPABILITY_NOT_SUPPORTED",
                provider_name,
            )
        if not hasattr(cap, method):
            raise APIError(
                f"能力 '{capability.value}' 不存在方法 '{method}'",
                "METHOD_NOT_FOUND",
                provider_name,
            )
        return await getattr(cap, method)(*args, **kwargs)

    def reload_config(self) -> None:
        """重新加载配置并重新初始化实例"""
        llm_config_manager.reload()
        self._providers.clear()
        self._init_providers()


llm_manager = LLMManager()


__all__ = ["LLMManager", "llm_manager"]
