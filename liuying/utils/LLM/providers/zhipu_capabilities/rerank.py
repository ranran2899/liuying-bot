"""智谱 AI 文本重排序能力实现"""
from typing import Any

from liuying.utils.LLM.zhi_pu.client import ZhipuClient


class ZhipuRerankCapability:
    """智谱 AI 文本重排序能力"""

    def __init__(self, client: ZhipuClient | None = None):
        """初始化重排序能力

        Args:
            client: 智谱客户端实例
        """
        self._client = client or ZhipuClient()

    async def rerank(
        self,
        query: str,
        documents: list[str],
        model: str = "rerank",
        top_n: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """文本重排序

        Args:
            query: 查询文本
            documents: 待排序文档列表
            model: 重排序模型名称
            top_n: 返回前 N 个结果
            options: 额外选项

        Returns:
            重排序结果列表
        """
        request_data: dict[str, Any] = {
            "model": model,
            "query": query,
            "documents": documents,
            "return_documents": True,
        }

        if top_n:
            request_data["top_n"] = top_n
        if options:
            request_data.update(options)

        response = await self._client.post("rerank", request_data)

        results: list[dict[str, Any]] = []
        for item in response.get("results", []):
            if not isinstance(item, dict):
                continue
            doc = item.get("document", {})
            results.append({
                "index": item.get("index"),
                "document": doc.get("text", "") if isinstance(doc, dict) else "",
                "score": item.get("relevance_score", 0),
            })
        return results

    async def rerank_with_threshold(
        self,
        query: str,
        documents: list[str],
        model: str = "rerank",
        threshold: float = 0.5,
        options: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """带分数阈值的重排序

        Args:
            query: 查询文本
            documents: 文档列表
            model: 模型名称
            threshold: 相关性分数阈值
            options: 额外选项

        Returns:
            过滤后的结果列表
        """
        results = await self.rerank(query, documents, model, options=options)
        return [r for r in results if r.get("score", 0) >= threshold]


__all__ = ["ZhipuRerankCapability"]
