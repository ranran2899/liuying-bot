"""智谱 AI 图像生成能力实现"""
from typing import Any

from liuying.utils.LLM.utils import ResponseParser
from liuying.utils.LLM.zhi_pu.client import ZhipuClient


class ZhipuImageCapability:
    """智谱 AI 图像生成能力（CogView 模型）"""

    def __init__(self, client: ZhipuClient | None = None):
        """初始化图像能力

        Args:
            client: 智谱客户端实例
        """
        self._client = client or ZhipuClient()

    async def generate(
        self,
        prompt: str,
        model: str = "CogView-3-Flash",
        size: str = "1024x1024",
        n: int = 1,
        options: dict[str, Any] | None = None,
    ) -> list[str]:
        """生成图像

        Args:
            prompt: 图像描述文本
            model: 模型名称
            size: 图像尺寸
            n: 生成数量
            options: 额外选项

        Returns:
            生成的图像 URL 列表
        """
        request_data: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "size": size,
            "n": n,
        }
        if options:
            request_data.update(options)
        else:
            request_data["quality"] = "standard"

        response = await self._client.post(
            "images/generations", request_data, timeout=120
        )
        return ResponseParser.parse_image_response(response)

    async def edit(
        self,
        image: str,
        prompt: str,
        mask: str | None = None,
        model: str = "CogView-3-Flash",
        size: str = "1024x1024",
        n: int = 1,
        options: dict[str, Any] | None = None,
    ) -> list[str]:
        """编辑图像

        Args:
            image: 原始图像 URL 或 Base64
            prompt: 编辑描述
            mask: 蒙版图像（智谱暂不支持，保留接口统一）
            model: 模型名称
            size: 图像尺寸
            n: 生成数量
            options: 额外选项

        Returns:
            编辑后的图像 URL 列表
        """
        request_data: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "image": image,
            "n": n,
            "size": size,
        }
        if mask:
            request_data["mask"] = mask
        if options:
            request_data.update(options)

        response = await self._client.post(
            "images/edits", request_data, timeout=120
        )
        return ResponseParser.parse_image_response(response)

    async def create_variation(
        self,
        image: str,
        model: str = "CogView-3-Flash",
        size: str = "1024x1024",
        n: int = 1,
        options: dict[str, Any] | None = None,
    ) -> list[str]:
        """创建图像变体

        Args:
            image: 原始图像 URL 或 Base64
            model: 模型名称
            size: 图像尺寸
            n: 生成数量
            options: 额外选项

        Returns:
            变体图像 URL 列表
        """
        request_data: dict[str, Any] = {
            "model": model,
            "image": image,
            "n": n,
            "size": size,
        }
        if options:
            request_data.update(options)

        response = await self._client.post(
            "images/variations", request_data, timeout=120
        )
        return ResponseParser.parse_image_response(response)


__all__ = ["ZhipuImageCapability"]
