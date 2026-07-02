"""智谱AI基础客户端"""
from typing import Any

from ..client_base import BaseLLMClient
from ..configs import ProviderConfig, get_all_providers, get_provider_config


class ZhipuClient(BaseLLMClient):
    """智谱AI API基础客户端"""

    DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

    def __init__(self, api_key: str | None = None, api_base: str | None = None):
        """初始化客户端

        Args:
            api_key: API密钥，如果不传则从配置中获取
            api_base: API基础URL，如果不传则从配置中获取
        """
        super().__init__("zhipu")
        provider_cfg = self._find_zhipu_provider()
        self._api_key = api_key or self._load_api_key(provider_cfg)
        self._base_url = api_base or self._load_api_base(provider_cfg)

    def get_provider_config(self) -> ProviderConfig | None:
        """获取当前提供商配置

        Returns:
            提供商配置对象，不存在则返回None
        """
        return self._find_zhipu_provider()

    def _find_zhipu_provider(self) -> ProviderConfig | None:
        """查找智谱AI提供商配置

        Returns:
            提供商配置对象，不存在则返回None
        """
        if provider_cfg := get_provider_config("zhipu"):
            return provider_cfg

        return next(
            (p for p in get_all_providers() if p.api_type == "zhipu" and p.api_key),
            None,
        )

    def _load_api_key(self, provider_cfg: ProviderConfig | None) -> str:
        """从配置加载API密钥

        Args:
            provider_cfg: 提供商配置对象

        Returns:
            API密钥
        """
        if provider_cfg and provider_cfg.api_key:
            return provider_cfg.api_key
        return ""

    def _load_api_base(self, provider_cfg: ProviderConfig | None) -> str:
        """从配置加载API基础URL

        Args:
            provider_cfg: 提供商配置对象

        Returns:
            API基础URL
        """
        if provider_cfg and provider_cfg.api_base:
            return provider_cfg.api_base
        return self.DEFAULT_BASE_URL

    @property
    def api_key(self) -> str:
        """获取API密钥"""
        if not self._api_key:
            raise ValueError("智谱AI API Key未配置")
        return self._api_key

    @property
    def base_url(self) -> str:
        """获取API基础URL"""
        return self._base_url

    def get_headers(self, content_type: str = "application/json") -> dict[str, str]:
        """构建请求头

        Args:
            content_type: 内容类型

        Returns:
            请求头字典
        """
        return self.build_headers(self.api_key, content_type=content_type)

    async def post(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        timeout: int = 60,
        **kwargs,
    ) -> Any:
        """发送POST请求

        Args:
            endpoint: API端点路径
            data: 请求数据
            timeout: 超时时间（秒）
            **kwargs: 额外参数

        Returns:
            API响应数据
        """
        headers = self.get_headers()
        response = await self.post_json(
            self._base_url, endpoint, data, headers, timeout, **kwargs
        )
        return self.check_response(response)

    async def post_multipart(
        self,
        endpoint: str,
        files: dict[str, Any],
        data: dict[str, Any] | None = None,
        timeout: int = 120,
    ) -> Any:
        """发送multipart POST请求（用于文件上传）

        Args:
            endpoint: API端点路径
            files: 文件数据
            data: 额外表单数据
            timeout: 超时时间（秒）

        Returns:
            API响应数据
        """
        headers = {"Authorization": f"Bearer {self.api_key}"}
        return await super().post_multipart(
            self._base_url, endpoint, files, data, headers, timeout
        )

    async def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        timeout: int = 60,
    ) -> Any:
        """发送GET请求

        Args:
            endpoint: API端点路径
            params: 查询参数
            timeout: 超时时间（秒）

        Returns:
            API响应数据
        """
        headers = self.get_headers()
        response = await self.get_json(
            self._base_url, endpoint, headers, params, timeout
        )
        return self.check_response(response)


__all__ = ["ZhipuClient"]
