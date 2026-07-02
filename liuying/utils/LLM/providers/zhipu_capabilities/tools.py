"""智谱 AI 工具能力实现"""
from typing import Any

from liuying.utils.LLM.zhi_pu.tools import ToolsAPI


class ZhipuToolsCapability:
    """智谱 AI 工具能力（网络搜索、网页阅读等）"""

    def __init__(self, client):
        """初始化工具能力

        Args:
            client: 智谱客户端实例
        """
        self._api = ToolsAPI(client)

    async def web_search(
        self,
        query: str,
        engine: str = "search_pro",
        count: int = 10,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """网络搜索

        Args:
            query: 搜索关键词
            engine: 搜索引擎类型
            count: 返回结果数量
            options: 额外选项

        Returns:
            搜索结果字典
        """
        options = options or {}
        return await self._api.web_search(
            query=query,
            search_engine=engine,
            count=count,
            **options,
        )

    async def web_read(
        self,
        url: str,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """网页阅读

        Args:
            url: 网页 URL
            options: 额外选项

        Returns:
            网页内容字典
        """
        options = options or {}
        return await self._api.web_read(url, **options)


__all__ = ["ZhipuToolsCapability"]
