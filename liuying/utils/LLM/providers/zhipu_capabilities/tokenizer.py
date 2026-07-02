"""智谱 AI 分词能力实现"""
from typing import Any

from liuying.utils.LLM.zhi_pu.client import ZhipuClient


class ZhipuTokenizerCapability:
    """智谱 AI 分词能力（Token 计数和编码）"""

    def __init__(self, client: ZhipuClient | None = None):
        """初始化分词能力

        Args:
            client: 智谱客户端实例
        """
        self._client = client or ZhipuClient()

    async def count(
        self,
        text: str | list[dict[str, str]],
        model: str = "glm-4",
    ) -> int:
        """计算文本或消息列表的 token 数量

        Args:
            text: 输入文本或消息列表
            model: 模型名称

        Returns:
            token 数量
        """
        if isinstance(text, list):
            total = 0
            for message in text:
                content = message.get("content", "")
                total += await self._count_text(content, model)
            return total
        return await self._count_text(text, model)

    async def _count_text(self, text: str, model: str) -> int:
        """计算单段文本的 token 数量

        Args:
            text: 输入文本
            model: 模型名称

        Returns:
            token 数量
        """
        request_data: dict[str, Any] = {"model": model, "text": text}
        result = await self._client.post("tokenizer/tokenize", request_data)
        return result.get("total_tokens", 0)

    def estimate(self, text: str) -> int:
        """快速估算 token 数量（基于字符数，不调用 API）

        Args:
            text: 输入文本

        Returns:
            估算的 token 数量
        """
        chinese_chars = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
        other_chars = len(text) - chinese_chars
        estimated = int(chinese_chars * 1.5 + other_chars / 4)
        return max(estimated, 1)


__all__ = ["ZhipuTokenizerCapability"]
