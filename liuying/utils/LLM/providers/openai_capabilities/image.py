"""OpenAI 兼容 API 图像生成能力实现"""
from typing import Any

from liuying.utils.LLM.open_ai.client import OpenAIClient
from liuying.utils.LLM.utils import APIError, ResponseParser


class OpenAIImageCapability:
    """OpenAI 兼容 API 图像生成能力"""

    def __init__(self, client: OpenAIClient | None = None):
        """初始化图像能力

        Args:
            client: OpenAI 客户端实例
        """
        self._client = client or OpenAIClient()

    async def generate(
        self,
        prompt: str,
        model: str = "dall-e-3",
        size: str = "1024x1024",
        n: int = 1,
        options: dict[str, Any] | None = None,
    ) -> list[str]:
        """生成图片

        Args:
            prompt: 图片描述
            model: 模型名称
            size: 图片尺寸
            n: 生成数量
            options: 额外选项

        Returns:
            图片 URL 列表
        """
        provider = self._client.get_random_provider()

        request_data: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "size": size,
            "n": n,
            "response_format": "url",
        }
        if options:
            request_data.update(options)

        response = await self._client.post(
            provider, "images/generations", request_data, timeout=120
        )

        if not isinstance(response, dict):
            raise APIError(
                f"响应格式错误: {response}", "INVALID_RESPONSE", "openai"
            )

        return ResponseParser.parse_image_response(response)

    async def edit(
        self,
        image: str,
        prompt: str,
        mask: str | None = None,
        model: str = "dall-e-2",
        size: str = "1024x1024",
        n: int = 1,
        options: dict[str, Any] | None = None,
    ) -> list[str]:
        """编辑图片

        Args:
            image: 原始图片路径或 URL
            prompt: 编辑描述
            mask: 蒙版图片路径或 URL
            model: 模型名称
            size: 图片尺寸
            n: 生成数量
            options: 额外选项

        Returns:
            图片 URL 列表
        """
        provider = self._client.get_random_provider()

        request_data: dict[str, Any] = {
            "model": model,
            "image": image,
            "prompt": prompt,
            "size": size,
            "n": n,
            "response_format": "url",
        }
        if mask:
            request_data["mask"] = mask
        if options:
            request_data.update(options)

        response = await self._client.post(
            provider, "images/edits", request_data, timeout=120
        )

        if not isinstance(response, dict):
            raise APIError(
                f"响应格式错误: {response}", "INVALID_RESPONSE", "openai"
            )

        return ResponseParser.parse_image_response(response)

    async def create_variation(
        self,
        image: str,
        model: str = "dall-e-2",
        size: str = "1024x1024",
        n: int = 1,
        options: dict[str, Any] | None = None,
    ) -> list[str]:
        """创建图片变体

        Args:
            image: 原始图片路径或 URL
            model: 模型名称
            size: 图片尺寸
            n: 生成数量
            options: 额外选项

        Returns:
            图片 URL 列表
        """
        provider = self._client.get_random_provider()

        request_data: dict[str, Any] = {
            "model": model,
            "image": image,
            "size": size,
            "n": n,
            "response_format": "url",
        }
        if options:
            request_data.update(options)

        response = await self._client.post(
            provider, "images/variations", request_data, timeout=120
        )

        if not isinstance(response, dict):
            raise APIError(
                f"响应格式错误: {response}", "INVALID_RESPONSE", "openai"
            )

        return ResponseParser.parse_image_response(response)


__all__ = ["OpenAIImageCapability"]
