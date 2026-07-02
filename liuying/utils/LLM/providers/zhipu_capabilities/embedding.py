"""智谱 AI 文本嵌入能力实现"""
from typing import Any

from liuying.utils.LLM.zhi_pu.client import ZhipuClient


class ZhipuEmbeddingCapability:
    """智谱 AI 文本嵌入能力（embedding-3/2）"""

    def __init__(self, client: ZhipuClient | None = None):
        """初始化文本嵌入能力

        Args:
            client: 智谱客户端实例
        """
        self._client = client or ZhipuClient()

    async def create(
        self,
        input_text: str | list[str],
        model: str = "embedding-3",
        dimensions: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> list[list[float]]:
        """创建文本嵌入向量

        Args:
            input_text: 输入文本或文本列表
            model: 嵌入模型名称
            dimensions: 嵌入维度
            options: 额外选项

        Returns:
            嵌入向量列表
        """
        request_data: dict[str, Any] = {
            "model": model,
            "input": input_text,
        }

        if dimensions:
            request_data["dimensions"] = dimensions
        if options:
            request_data.update(options)

        response = await self._client.post("embeddings", request_data)

        embeddings: list[list[float]] = []
        for item in response.get("data", []):
            if isinstance(item, dict) and "embedding" in item:
                embeddings.append(item["embedding"])
        return embeddings

    async def create_batch(
        self,
        texts: list[str],
        model: str = "embedding-3",
        batch_size: int = 100,
        dimensions: int | None = None,
    ) -> list[list[float]]:
        """批量创建文本嵌入（自动分批处理）

        Args:
            texts: 文本列表
            model: 模型名称
            batch_size: 每批处理数量
            dimensions: 嵌入维度

        Returns:
            嵌入向量列表
        """
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            embeddings = await self.create(batch, model, dimensions)
            all_embeddings.extend(embeddings)

        return all_embeddings

    def get_dimension(self, model: str) -> int:
        """获取模型的默认嵌入维度

        Args:
            model: 模型名称

        Returns:
            嵌入维度数
        """
        dimension_map: dict[str, int] = {
            "embedding-3": 2048,
            "embedding-2": 1024,
        }
        return dimension_map.get(model, 1024)


__all__ = ["ZhipuEmbeddingCapability"]
