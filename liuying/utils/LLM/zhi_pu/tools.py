"""智谱AI工具接口"""
from typing import Any, Literal

from liuying.utils.log import logger

from .client import ZhipuClient


class ToolsAPI:
    """智谱AI工具API（网络搜索、网页阅读等）"""

    def __init__(self, client: ZhipuClient | None = None):
        """初始化工具API

        Args:
            client: 智谱AI客户端实例
        """
        self._client = client or ZhipuClient()

    async def web_search(
        self,
        query: str,
        search_engine: Literal[
            "search_std", "search_pro", "search_pro_sogou", "search_pro_quark"
        ] = "search_pro",
        count: int = 10,
        search_intent: bool = False,
        search_domain_filter: str | None = None,
        search_recency_filter: Literal[
            "oneDay", "oneWeek", "oneMonth", "oneYear", "noLimit"
        ] = "noLimit",
        content_size: Literal["medium", "high"] = "medium",
        **kwargs,
    ) -> dict[str, Any]:
        """网络搜索

        Args:
            query: 搜索关键词，建议不超过70个字符
            search_engine: 搜索引擎类型
            count: 返回结果数量，范围1-50，默认10
            search_intent: 是否进行搜索意图识别，默认False
            search_domain_filter: 限定搜索域名白名单
            search_recency_filter: 搜索时间范围
            content_size: 返回内容大小
            **kwargs: 额外参数

        Returns:
            搜索结果，包含 search_result 列表
        """
        request_data: dict[str, Any] = {
            "search_query": query[:70],
            "search_engine": search_engine,
            "search_intent": search_intent,
            "count": min(max(count, 1), 50),
            "search_recency_filter": search_recency_filter,
            "content_size": content_size,
        }

        if search_domain_filter:
            request_data["search_domain_filter"] = search_domain_filter

        if kwargs:
            request_data.update(kwargs)

        return await self._client.post("web_search", request_data)

    async def web_read(
        self,
        url: str,
        **kwargs,
    ) -> dict[str, Any]:
        """网页阅读/内容提取

        Args:
            url: 要读取的网页URL
            **kwargs: 额外参数

        Returns:
            网页内容，包含 reader_result 字段
        """
        request_data: dict[str, Any] = {"url": url}

        if kwargs:
            request_data.update(kwargs)

        return await self._client.post("reader", request_data, timeout=120)

    async def search_and_summarize(
        self,
        query: str,
        max_results: int = 5,
        search_engine: Literal[
            "search_std", "search_pro", "search_pro_sogou", "search_pro_quark"
        ] = "search_std",
        **kwargs,
    ) -> dict[str, Any]:
        """搜索并总结

        Args:
            query: 搜索查询
            max_results: 最大结果数
            search_engine: 搜索引擎类型
            **kwargs: 额外参数

        Returns:
            包含搜索结果和摘要的字典
        """
        search_result = await self.web_search(
            query=query,
            search_engine=search_engine,
            count=max_results,
            **kwargs,
        )

        results = search_result.get("search_result", [])
        if not results:
            return {"search_results": [], "fetched_contents": [], "total": 0}

        urls = [r.get("link", "") for r in results[:max_results] if r.get("link")]
        contents: list[dict[str, Any]] = []

        for url in urls:
            try:
                content = await self.web_read(url, **kwargs)
                reader_result = content.get("reader_result", {})
                if reader_result and reader_result.get("content"):
                    contents.append({
                        "url": url,
                        "title": reader_result.get("title", ""),
                        "content": reader_result.get("content", ""),
                    })
            except Exception as e:
                logger.warning(f"读取网页失败 {url}: {e}")

        return {
            "search_results": results[:max_results],
            "fetched_contents": contents,
            "total": len(results),
        }


__all__ = ["ToolsAPI"]
