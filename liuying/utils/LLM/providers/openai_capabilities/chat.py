"""OpenAI 兼容 API 对话能力实现"""
import random
from typing import Any

from liuying.utils.http.http_utils import AsyncHttpx
from liuying.utils.LLM.configs import get_llm_config, get_model_config
from liuying.utils.LLM.open_ai.client import OpenAIClient
from liuying.utils.LLM.tracker import token_tracker
from liuying.utils.LLM.utils import APIError, MultiAPIError, ResponseParser
from liuying.utils.log import logger


class OpenAIChatCapability:
    """OpenAI 兼容 API 对话能力"""

    def __init__(self, client: OpenAIClient | None = None):
        """初始化对话能力

        Args:
            client: OpenAI 客户端实例
        """
        self._client = client or OpenAIClient()

    async def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        """调用 OpenAI 兼容 API 进行对话，支持多配置轮询

        Args:
            model: 模型名称
            messages: 对话消息列表
            options: 额外选项，支持标准键 reasoning_enabled 控制深度思考

        Returns:
            tuple[str, str]: (reasoning_content, content)
                - reasoning_content: 思考链内容，无思考链时为空串
                - content: 正常回复内容
        """
        providers = self._client.get_provider_configs()
        if not providers:
            raise APIError("未配置任何有效的OpenAI API配置", "NO_CONFIG", "openai")

        model_cfg_result = get_model_config(model)
        model_base_url = model_cfg_result[0].api_base if model_cfg_result else None

        candidates = (
            [p for p in providers if p.api_base == model_base_url]
            if model_base_url
            else providers
        )
        if not candidates:
            candidates = providers

        random.shuffle(candidates)
        errors: list[tuple[str, Exception]] = []

        for provider in candidates:
            try:
                is_ernie = "baidubce.com" in provider.api_base
                return await self._chat_request(
                    provider, model, messages, options, is_ernie
                )
            except Exception as e:
                errors.append((provider.api_base, e))
                logger.error(f"配置调用失败: {e}")

        raise MultiAPIError(errors)

    async def _chat_request(
        self,
        provider: Any,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
        is_ernie: bool = False,
    ) -> tuple[str, str]:
        """通用对话请求

        Args:
            provider: 提供商配置对象
            model: 模型名称
            messages: 对话消息列表
            options: 额外选项，支持标准键 reasoning_enabled 控制深度思考
            is_ernie: 是否为文心一言 API

        Returns:
            tuple[str, str]: (reasoning_content, content)
        """
        base_url = provider.api_base.rstrip("/")
        url = base_url if is_ernie else f"{base_url}/chat/completions"

        actual_model = model
        if model_cfg_result := get_model_config(model):
            actual_model = model_cfg_result[1].model_name or actual_model

        options = options or {}
        reasoning_enabled = options.pop("reasoning_enabled", False)

        defaults = get_llm_config().request_defaults
        request_data: dict[str, Any] = {
            "model": actual_model,
            "messages": messages,
            **defaults.to_dict(),
        }
        if options:
            request_data.update(options)
            if options.get("baseUrl"):
                custom_url = options.pop("baseUrl").rstrip("/")
                url = custom_url if is_ernie else f"{custom_url}/chat/completions"

        if reasoning_enabled:
            request_data["reasoning_effort"] = "medium"

        headers = self._client.get_headers(provider)
        if is_ernie and provider.api_key:
            url = f"{url}?access_token={provider.api_key}"
            headers.pop("Authorization", None)

        endpoint = url.replace(provider.api_base.rstrip("/") + "/", "")
        response = await self._client.post(
            provider, endpoint, request_data, timeout=60
        )

        if not isinstance(response, dict):
            raise APIError(
                f"响应格式错误: {response}", "INVALID_RESPONSE", "openai"
            )

        result = ResponseParser.parse_chat_response(
            response, "ernie" if is_ernie else "openai"
        )
        await token_tracker.record(
            provider=provider.name,
            model=model,
            **ResponseParser.extract_usage(response),
        )
        return result

    async def chat_stream(
        self,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
    ) -> Any:
        """流式调用 OpenAI 兼容 API

        Args:
            model: 模型名称
            messages: 对话消息列表
            options: 额外选项，支持标准键 reasoning_enabled 控制深度思考

        Yields:
            流式响应的文本片段
        """
        provider = self._client.get_random_provider()
        base_url = self._client.get_base_url(provider)
        url = f"{base_url}/chat/completions"

        options = options or {}
        reasoning_enabled = options.pop("reasoning_enabled", False)

        defaults = get_llm_config().request_defaults
        request_data: dict[str, Any] = {
            "model": model,
            "messages": messages,
            **defaults.to_dict(),
            "stream": True,
        }
        if options:
            request_data.update(options)

        if reasoning_enabled:
            request_data["reasoning_effort"] = "medium"

        headers = self._client.get_headers(provider)

        async for chunk in AsyncHttpx.post_stream(
            url=url, json=request_data, headers=headers, timeout=60
        ):
            if chunk and isinstance(chunk, dict):
                content = (
                    chunk.get("choices", [{}])[0]
                    .get("delta", {})
                    .get("content", "")
                )
                if content:
                    yield content

    async def generate(
        self,
        model: str,
        prompt: str,
        options: dict[str, Any] | None = None,
    ) -> str:
        """生成接口 - 将 prompt 转换为 messages

        Args:
            model: 模型名称
            prompt: 用户输入
            options: 额外选项

        Returns:
            模型生成文本
        """
        return await self.chat(
            model, [{"role": "user", "content": prompt}], options
        )


__all__ = ["OpenAIChatCapability"]
