"""LLM客户端基类，提供通用HTTP请求和响应处理能力"""
from abc import ABC, abstractmethod
from typing import Any

from liuying.utils.http.http_utils import AsyncHttpx
from liuying.utils.log import logger

from .configs import ProviderConfig, get_llm_config
from .utils import APIError


class BaseLLMClient(ABC):
    """LLM客户端基类，封装通用HTTP请求逻辑"""

    def __init__(self, provider_name: str):
        """初始化客户端基类

        Args:
            provider_name: 提供商名称，用于日志和错误信息
        """
        self._provider_name = provider_name
        self._client_settings = get_llm_config().client_settings

    @property
    def provider_name(self) -> str:
        """获取提供商名称

        Returns:
            提供商名称
        """
        return self._provider_name

    @property
    def timeout(self) -> int:
        """获取超时配置

        Returns:
            超时时间（秒）
        """
        return self._client_settings.timeout

    @property
    def max_retries(self) -> int:
        """获取最大重试次数

        Returns:
            最大重试次数
        """
        return self._client_settings.max_retries

    def build_headers(
        self,
        api_key: str,
        extra_headers: dict[str, str] | None = None,
        content_type: str = "application/json",
    ) -> dict[str, str]:
        """构建请求头

        Args:
            api_key: API密钥
            extra_headers: 额外请求头
            content_type: 内容类型

        Returns:
            请求头字典
        """
        headers: dict[str, str] = {"Content-Type": content_type}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def build_url(self, base_url: str, endpoint: str) -> str:
        """构建完整URL

        Args:
            base_url: 基础URL
            endpoint: API端点路径

        Returns:
            完整URL
        """
        return f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"

    async def post_json(
        self,
        base_url: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 60,
        **kwargs,
    ) -> Any:
        """发送POST请求并解析JSON响应

        Args:
            base_url: 基础URL
            endpoint: API端点路径
            data: 请求数据
            headers: 请求头
            timeout: 超时时间（秒）
            **kwargs: 额外参数

        Returns:
            API响应数据
        """
        url = self.build_url(base_url, endpoint)
        logger.info(f"调用{self._provider_name} API: {endpoint}")
        return await AsyncHttpx.post_json(
            url=url,
            json=data,
            headers=headers,
            timeout=timeout,
            raise_on_failure=True,
            **kwargs,
        )

    async def post_raw(
        self,
        base_url: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 60,
    ) -> Any:
        """发送POST请求并返回原始响应

        Args:
            base_url: 基础URL
            endpoint: API端点路径
            data: 请求数据
            headers: 请求头
            timeout: 超时时间（秒）

        Returns:
            原始响应数据
        """
        url = self.build_url(base_url, endpoint)
        logger.info(f"调用{self._provider_name} API (原始): {endpoint}")
        return await AsyncHttpx.post(
            url=url, json=data, headers=headers, timeout=timeout
        )

    async def get_json(
        self,
        base_url: str,
        endpoint: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        timeout: int = 60,
    ) -> Any:
        """发送GET请求并解析JSON响应

        Args:
            base_url: 基础URL
            endpoint: API端点路径
            headers: 请求头
            params: 查询参数
            timeout: 超时时间（秒）

        Returns:
            API响应数据
        """
        url = self.build_url(base_url, endpoint)
        logger.info(f"调用{self._provider_name} API (GET): {endpoint}")
        response = await AsyncHttpx.get(
            url=url, headers=headers, params=params, timeout=timeout
        )

        if not hasattr(response, "json"):
            raise APIError("响应格式错误", "INVALID_RESPONSE", self._provider_name)

        return response.json()

    async def post_multipart(
        self,
        base_url: str,
        endpoint: str,
        files: dict[str, Any],
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 120,
    ) -> Any:
        """发送multipart POST请求（用于文件上传）

        Args:
            base_url: 基础URL
            endpoint: API端点路径
            files: 文件数据
            data: 额外表单数据
            headers: 请求头
            timeout: 超时时间（秒）

        Returns:
            API响应数据
        """
        url = self.build_url(base_url, endpoint)
        logger.info(f"调用{self._provider_name} API (文件上传): {endpoint}")
        response = await AsyncHttpx.post(
            url=url, files=files, data=data, headers=headers, timeout=timeout
        )

        if not hasattr(response, "json"):
            raise APIError(
                "响应格式错误", "INVALID_RESPONSE", self._provider_name
            )

        return self.check_response(response.json())

    def check_response(self, response: Any) -> Any:
        """检查API响应

        Args:
            response: API响应数据

        Returns:
            响应数据

        Raises:
            APIError: 当API返回错误时
        """
        if not response:
            raise APIError(
                "API请求失败: 未收到响应", "NO_RESPONSE", self._provider_name
            )

        if isinstance(response, dict):
            if "error" in response:
                error_info = response["error"]
                match error_info:
                    case dict():
                        msg = error_info.get("message", str(error_info))
                        code = error_info.get("code", "UNKNOWN")
                    case _:
                        msg = str(error_info)
                        code = "UNKNOWN"
                raise APIError(
                    f"{self._provider_name} API错误 [{code}]: {msg}",
                    code,
                    self._provider_name,
                )
            return response

        raise APIError(
            f"API返回格式错误: {type(response)}",
            "INVALID_RESPONSE",
            self._provider_name,
        )

    @abstractmethod
    def get_provider_config(self) -> ProviderConfig | None:
        """获取当前提供商配置

        Returns:
            提供商配置对象，不存在则返回None
        """
        ...


__all__ = ["BaseLLMClient"]
