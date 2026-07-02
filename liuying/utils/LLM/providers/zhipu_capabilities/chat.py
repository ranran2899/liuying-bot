"""智谱 AI 对话能力实现"""
from typing import Any

from liuying.utils.http.http_utils import AsyncHttpx
from liuying.utils.LLM.configs import get_llm_config, get_model_config
from liuying.utils.LLM.tracker import token_tracker
from liuying.utils.LLM.utils import ResponseParser
from liuying.utils.LLM.zhi_pu.client import ZhipuClient
from liuying.utils.log import logger


class ZhipuChatCapability:
    """智谱 AI 对话能力"""

    def __init__(self, client: ZhipuClient | None = None):
        """初始化对话能力

        Args:
            client: 智谱客户端实例
        """
        self._client = client or ZhipuClient()

    async def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        """调用智谱 AI 大模型进行对话

        Args:
            model: 模型名称
            messages: 对话消息列表
            options: 额外选项，支持标准键 reasoning_enabled 控制深度思考

        Returns:
            tuple[str, str]: (reasoning_content, content)
                - reasoning_content: 思考链内容，无思考链时为空串
                - content: 正常回复内容
        """
        model_cfg_result = get_model_config(model)
        actual_model = model_cfg_result[1].model_name if model_cfg_result else model

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

        request_data["thinking"] = {
            "type": "enabled" if reasoning_enabled else "disabled"
        }

        logger.info(f"智谱AI对话: {actual_model}")

        response = await self._client.post("chat/completions", request_data)
        result = ResponseParser.parse_chat_response(response, "zhipu")
        provider_cfg = self._client.get_provider_config()
        await token_tracker.record(
            provider=provider_cfg.name if provider_cfg else "zhipu",
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
        """流式调用智谱 AI 大模型

        Args:
            model: 模型名称
            messages: 对话消息列表
            options: 额外选项，支持标准键 reasoning_enabled 控制深度思考

        Yields:
            流式响应的文本片段
        """
        model_cfg_result = get_model_config(model)
        actual_model = model_cfg_result[1].model_name if model_cfg_result else model

        options = options or {}
        reasoning_enabled = options.pop("reasoning_enabled", False)

        defaults = get_llm_config().request_defaults
        request_data: dict[str, Any] = {
            "model": actual_model,
            "messages": messages,
            **defaults.to_dict(),
            "stream": True,
        }

        if options:
            request_data.update(options)

        request_data["thinking"] = {
            "type": "enabled" if reasoning_enabled else "disabled"
        }

        url = f"{self._client.base_url}/chat/completions"
        headers = self._client.get_headers()

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


__all__ = ["ZhipuChatCapability"]
