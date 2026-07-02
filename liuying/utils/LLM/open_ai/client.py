"""OpenAI兼容API基础客户端"""
import random
from typing import Any

from ..client_base import BaseLLMClient
from ..configs import ProviderConfig, get_all_providers
from ..utils import APIError, ResponseValidator


class OpenAIClient(BaseLLMClient):
    """OpenAI兼容API基础客户端"""

    def __init__(self):
        """初始化客户端"""
        super().__init__("openai")
        self._provider_configs: list[ProviderConfig] | None = None

    def get_provider_config(self) -> ProviderConfig | None:
        """获取当前提供商配置

        Returns:
            提供商配置对象，不存在则返回None
        """
        configs = self.get_provider_configs()
        return random.choice(configs) if configs else None

    def get_provider_configs(self) -> list[ProviderConfig]:
        """获取所有OpenAI兼容的提供商配置

        Returns:
            提供商配置列表
        """
        if self._provider_configs is not None:
            return self._provider_configs

        self._provider_configs = [
            p
            for p in get_all_providers()
            if p.is_openai_compatible
        ]
        return self._provider_configs

    def get_random_provider(self) -> ProviderConfig:
        """随机获取一个有效提供商配置

        Returns:
            提供商配置对象

        Raises:
            APIError: 当没有有效配置时
        """
        configs = self.get_provider_configs()
        if not configs:
            raise APIError("未配置任何有效的OpenAI API配置", "NO_CONFIG", "openai")
        return random.choice(configs)

    def get_headers(self, provider: ProviderConfig) -> dict[str, str]:
        """构建请求头

        Args:
            provider: 提供商配置对象

        Returns:
            请求头字典
        """
        return self.build_headers(
            api_key=provider.api_key,
            extra_headers=provider.extra_headers,
        )

    def get_base_url(self, provider: ProviderConfig) -> str:
        """获取提供商的基础URL

        Args:
            provider: 提供商配置对象

        Returns:
            基础URL
        """
        return provider.api_base.rstrip("/")

    async def post(
        self,
        provider: ProviderConfig,
        endpoint: str,
        data: dict[str, Any] | None = None,
        timeout: int = 60,
        **kwargs,
    ) -> Any:
        """发送POST请求

        Args:
            provider: 提供商配置对象
            endpoint: API端点路径
            data: 请求数据
            timeout: 超时时间（秒）
            **kwargs: 额外参数

        Returns:
            API响应数据
        """
        base_url = self.get_base_url(provider)
        headers = self.get_headers(provider)
        return await self.post_json(
            base_url, endpoint, data, headers, timeout, **kwargs
        )

    async def post_raw(
        self,
        provider: ProviderConfig,
        endpoint: str,
        data: dict[str, Any] | None = None,
        timeout: int = 60,
    ) -> Any:
        """发送POST请求并返回原始响应

        Args:
            provider: 提供商配置对象
            endpoint: API端点路径
            data: 请求数据
            timeout: 超时时间（秒）

        Returns:
            原始响应数据
        """
        base_url = self.get_base_url(provider)
        headers = self.get_headers(provider)
        return await super().post_raw(
            base_url, endpoint, data, headers, timeout
        )

    async def get(
        self,
        provider: ProviderConfig,
        endpoint: str,
        params: dict[str, Any] | None = None,
        timeout: int = 60,
    ) -> Any:
        """发送GET请求

        Args:
            provider: 提供商配置对象
            endpoint: API端点路径
            params: 查询参数
            timeout: 超时时间（秒）

        Returns:
            API响应数据
        """
        base_url = self.get_base_url(provider)
        headers = self.get_headers(provider)
        return await self.get_json(
            base_url, endpoint, headers, params, timeout
        )

    def check_response(self, response: Any, is_ernie: bool = False) -> Any:
        """检查API响应

        Args:
            response: API响应数据
            is_ernie: 是否为文心一言API

        Returns:
            响应数据

        Raises:
            APIError: 当API返回错误时
        """
        provider = "ernie" if is_ernie else "openai"
        ResponseValidator.check_error(
            response if isinstance(response, dict) else None, provider
        )

        if is_ernie and isinstance(response, dict):
            if response.get("error_code", 0) != 0:
                raise APIError(
                    f"ERNIE API失败: {response.get('error_msg', '未知错误')}",
                    str(response.get("error_code", "UNKNOWN")),
                    "ernie",
                )

        return response

    def invalidate_cache(self) -> None:
        """清除配置缓存，下次访问时重新加载"""
        self._provider_configs = None


__all__ = ["OpenAIClient"]
