"""智谱AI基础客户端

按 model 动态路由到正确的 provider 配置。
当存在多个同 api_type 的 provider（如多个 zhipu 配置各自挂载不同模型）时，
根据请求的 model 从配置中查找匹配的 ProviderConfig，并使用其 api_key、
api_base 与 extra_headers，避免用错 key 调用错模型。
"""
from typing import Any

from ..client_base import BaseLLMClient
from ..configs import (
    ModelConfig,
    ProviderConfig,
    get_all_providers,
    get_model_config,
    get_provider_config,
)


class ZhipuClient(BaseLLMClient):
    """智谱AI API基础客户端

    通过显式传入的 ``api_key``/``api_base`` 兼容旧用法；未传入时，
    所有请求方法在内部按 ``model`` 动态解析正确的 ProviderConfig，
    保证多 GLM 配置下不同模型请求落到正确的 key 与 base。
    """

    DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

    def __init__(self, api_key: str | None = None, api_base: str | None = None):
        """初始化客户端

        参数:
            api_key: 显式 API 密钥。传值时使用该值，跳过 model 路由。
            api_base: 显式 API 基础 URL。传值时使用该值，跳过 model 路由。
        """
        super().__init__("zhipu")
        self._explicit_api_key = api_key
        self._explicit_api_base = api_base

    def get_provider_config(
        self, model: str | None = None
    ) -> ProviderConfig | None:
        """获取当前请求应使用的提供商配置

        参数:
            model: 模型名，传入时按 model 路由到对应 provider；
                None 时回退到默认 zhipu provider。

        返回:
            ProviderConfig 或 None
        """
        return self._resolve_provider(model)

    def _resolve_provider(self, model: str | None) -> ProviderConfig | None:
        """解析指定 model 对应的 provider 配置

        优先级：model 配置 -> 名为 zhipu 的 provider ->
        第一个 api_type=zhipu 的 provider。显式 api_key/api_base
        模式下返回 None，由调用方使用显式配置。

        参数:
            model: 模型名，可为 None

        返回:
            解析到的 ProviderConfig；解析不到返回 None
        """
        return self._resolve_provider(model)

    def _resolve_provider(self, model: str | None) -> ProviderConfig | None:
        """解析指定 model 对应的 provider 配置

        优先级：model 配置 -> 名为 zhipu 的 provider ->
        第一个 api_type=zhipu 的 provider。显式 api_key/api_base
        模式下返回 None，由调用方使用显式配置。

        参数:
            model: 模型名，可为 None

        返回:
            解析到的 ProviderConfig；解析不到返回 None
        """
        if self._explicit_api_key or self._explicit_api_base:
            return None

        if model:
            model_cfg = get_model_config(model)
            if model_cfg is not None:
                return model_cfg[0]

        if provider_cfg := get_provider_config("zhipu"):
            return provider_cfg

        return next(
            (
                p
                for p in get_all_providers()
                if p.api_type == "zhipu" and p.api_key
            ),
            None,
        )

    def _resolve_for_model(
        self, model: str | None
    ) -> tuple[str, str, ProviderConfig | None, ModelConfig | None]:
        """根据 model 解析 (api_key, api_base, provider_cfg, model_cfg)

        显式传入的 api_key/api_base 直接覆盖；否则根据 model 找
        对应 provider 与 model 配置，找不到时回退到默认 zhipu 配置。

        参数:
            model: 模型名，可为 None

        返回:
            (api_key, api_base, provider_cfg, model_cfg) 元组
        """
        if self._explicit_api_key or self._explicit_api_base:
            return (
                self._explicit_api_key or "",
                self._explicit_api_base or self.DEFAULT_BASE_URL,
                None,
                None,
            )

        provider_cfg: ProviderConfig | None = None
        model_cfg: ModelConfig | None = None
        if model:
            model_lookup = get_model_config(model)
            if model_lookup is not None:
                provider_cfg, model_cfg = model_lookup

        if provider_cfg is None:
            provider_cfg = self._resolve_provider(model)

        if provider_cfg is None:
            return "", self.DEFAULT_BASE_URL, None, None

        return (
            provider_cfg.api_key or "",
            provider_cfg.api_base or self.DEFAULT_BASE_URL,
            provider_cfg,
            model_cfg,
        )

    @property
    def api_key(self) -> str:
        """获取默认 API 密钥（无 model 时）"""
        if self._explicit_api_key:
            return self._explicit_api_key
        key, _, _, _ = self._resolve_for_model(None)
        if not key:
            raise ValueError("智谱AI API Key未配置")
        return key

    @property
    def base_url(self) -> str:
        """获取默认 API 基础 URL（无 model 时）"""
        if self._explicit_api_base:
            return self._explicit_api_base
        _, base, _, _ = self._resolve_for_model(None)
        return base

    def get_base_url(self, model: str | None = None) -> str:
        """获取指定 model 对应的 API 基础 URL

        参数:
            model: 模型名，None 时返回默认 base URL

        返回:
            API 基础 URL
        """
        if self._explicit_api_base:
            return self._explicit_api_base
        _, base, _, _ = self._resolve_for_model(model)
        return base

    def get_headers(
        self,
        model: str | None = None,
        content_type: str = "application/json",
    ) -> dict[str, str]:
        """构建请求头，自动合并 provider 与 model 的 extra_headers

        参数:
            model: 模型名，可为 None
            content_type: 内容类型

        返回:
            请求头字典
        """
        api_key, _, provider_cfg, model_cfg = self._resolve_for_model(model)
        extra: dict[str, str] | None = None
        if model_cfg is not None and model_cfg.extra_headers:
            extra = dict(model_cfg.extra_headers)
        elif provider_cfg is not None and provider_cfg.extra_headers:
            extra = dict(provider_cfg.extra_headers)
        return self.build_headers(
            api_key=api_key, extra_headers=extra, content_type=content_type
        )

    async def post(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        timeout: int = 60,
        *,
        model: str | None = None,
        **kwargs,
    ) -> Any:
        """发送POST请求

        参数:
            endpoint: API 端点路径
            data: 请求数据
            timeout: 超时（秒）
            model: 模型名，用于按 model 路由到正确的 provider 配置
            **kwargs: 透传至 AsyncHttpx.post_json

        返回:
            解析后的响应数据
        """
        _, base_url, _, _ = self._resolve_for_model(model)
        headers = self.get_headers(model=model)
        response = await self.post_json(
            base_url=base_url,
            endpoint=endpoint,
            data=data,
            headers=headers,
            timeout=timeout,
            **kwargs,
        )
        return self.check_response(response)

    async def post_multipart(
        self,
        endpoint: str,
        files: dict[str, Any],
        data: dict[str, Any] | None = None,
        timeout: int = 120,
        *,
        model: str | None = None,
    ) -> Any:
        """发送 multipart POST 请求（文件上传）

        参数:
            endpoint: API 端点路径
            files: 文件数据
            data: 表单数据
            timeout: 超时（秒）
            model: 模型名，用于按 model 路由

        返回:
            解析后的响应数据
        """
        api_key, base_url, _, _ = self._resolve_for_model(model)
        headers = {
            "Authorization": f"Bearer {api_key}" if api_key else ""
        }
        return await super().post_multipart(
            base_url=base_url,
            endpoint=endpoint,
            files=files,
            data=data,
            headers=headers,
            timeout=timeout,
        )

    async def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        timeout: int = 60,
        *,
        model: str | None = None,
    ) -> Any:
        """发送GET请求

        参数:
            endpoint: API 端点路径
            params: 查询参数
            timeout: 超时（秒）
            model: 模型名，用于按 model 路由

        返回:
            解析后的响应数据
        """
        _, base_url, _, _ = self._resolve_for_model(model)
        headers = self.get_headers(model=model)
        return await self.get_json(
            base_url=base_url,
            endpoint=endpoint,
            headers=headers,
            params=params,
            timeout=timeout,
        )


__all__ = ["ZhipuClient"]
