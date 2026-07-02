"""搜索类内置工具

联网搜索 + 网页抓取。

联网搜索统一通过 llm_helper.web_search 调用，
由 liuying.utils.LLM 的 WebSearchCapability 提供正式 provider，
liuying/plugins/web_search 插件提供免配置降级兜底。
"""

from ....core.llm import llm_helper
from ....core.tools import web_fetch
from ...runtime.constants import (
    INTENT_TAG_NETWORK,
    INTENT_TAG_REALTIME,
    LATENCY_CLASS_NETWORK,
)
from ..decorators import register_tool


@register_tool(
    name="web_search",
    description=(
        "联网搜索最新信息（优先正式provider，自动降级到免配置客户端），"
        "适用于需要实时数据或最新事实的查询"
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索查询关键词",
            },
            "count": {
                "type": "integer",
                "description": "返回结果数量，默认5，最大10",
                "default": 5,
            },
        },
        "required": ["query"],
    },
    intent_tags=[INTENT_TAG_REALTIME, INTENT_TAG_NETWORK],
    latency_class=LATENCY_CLASS_NETWORK,
    requires_network=True,
    metadata={
        "fallback_strategy": "free_clients",
        "max_results": 10,
    },
)
async def web_search(query: str, count: int = 5) -> str:
    """执行联网搜索（带降级兜底）

    通过 llm_helper.web_search 调用统一 WebSearchCapability，
    正式 provider 未配置或失败时由免配置客户端自动降级。

    参数:
        query: 搜索查询关键词
        count: 返回结果数量，默认5

    返回:
        str: 搜索结果摘要文本
    """
    try:
        results = await llm_helper.web_search(
            query, count=min(max(count, 1), 10)
        )
        if not results:
            return "未找到相关结果"
        lines: list[str] = []
        for i, item in enumerate(results, 1):
            title = item.get("title", "") or "(无标题)"
            url = item.get("url", "") or ""
            snippet = item.get("snippet", "") or ""
            lines.append(
                f"{i}. {title}\n"
                f"   URL: {url}\n"
                f"   摘要: {snippet}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"搜索失败: {e}"


@register_tool(
    name="fetch_webpage",
    description=(
        "抓取指定URL的网页正文并格式化为AI可读上下文，"
        "适用于需要读取网页详细内容、解析文章正文时"
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "要抓取的网页URL",
            },
            "max_length": {
                "type": "integer",
                "description": "最大内容长度，默认4000，最大8000",
                "default": 4000,
            },
        },
        "required": ["url"],
    },
    intent_tags=[INTENT_TAG_NETWORK, INTENT_TAG_REALTIME],
    latency_class=LATENCY_CLASS_NETWORK,
    requires_network=True,
    metadata={"output_kind": "webpage_text"},
)
async def fetch_webpage(url: str, max_length: int = 4000) -> str:
    """抓取网页内容并格式化为上下文

    参数:
        url: 网页URL
        max_length: 最大内容长度，默认4000

    返回:
        str: 格式化的网页内容文本
    """
    try:
        return await web_fetch.fetch_as_context(
            url, max_length=min(max(max_length, 500), 8000)
        )
    except Exception as e:
        return f"网页抓取失败: {e}"
