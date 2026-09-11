"""新闻查询实现

通过 runtime.llm_helper.web_search 实现免配置新闻查询。
"""

from typing import Any

from liuying.liuying_plugins.AI.tools import AgentTool

_CATEGORY_KEYWORDS: dict[str, str] = {
    "general": "今日新闻",
    "tech": "科技新闻",
    "finance": "财经新闻",
    "sports": "体育新闻",
    "entertainment": "娱乐新闻",
    "world": "国际新闻",
}
"""新闻分类到搜索关键词映射"""

_MAX_NEWS_RESULTS = 5
"""新闻查询最大结果数"""


async def query_news(
    category: str = "general",
    llm_helper: Any = None,
) -> str:
    """查询新闻

    通过 llm_helper.web_search 按分类查询最新新闻。

    参数:
        category: 新闻分类，默认 general
        llm_helper: LLM助手实例

    返回:
        str: 新闻摘要文本
    """
    if llm_helper is None:
        return "新闻查询不可用：未配置LLM助手"
    category = (category or "general").lower()
    keyword = _CATEGORY_KEYWORDS.get(category, "今日新闻")
    try:
        results = await llm_helper.web_search(
            keyword, count=_MAX_NEWS_RESULTS
        )
        if not results:
            return f"未查询到 {keyword} 相关新闻"
        lines: list[str] = [f"[{category}]新闻摘要:"]
        for i, item in enumerate(results, 1):
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            url = item.get("url", "")
            lines.append(
                f"{i}. {title}\n   {snippet}\n   {url}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"新闻查询失败: {e}"


def build_news_tool(runtime: Any) -> AgentTool:
    """构建新闻查询工具

    参数:
        runtime: SkillRuntime 实例

    返回:
        AgentTool: 新闻查询工具
    """
    llm_helper = getattr(runtime, "llm_helper", None)

    async def _handler(category: str = "general") -> str:
        """新闻查询handler

        参数:
            category: 新闻分类

        返回:
            str: 新闻摘要
        """
        return await query_news(
            category=category, llm_helper=llm_helper
        )

    return AgentTool(
        name="get_news",
        description=(
            "查询最新新闻，支持分类："
            "general/tech/finance/sports/entertainment/world"
        ),
        parameters={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "新闻分类，默认 general",
                    "default": "general",
                },
            },
            "required": [],
        },
        func=_handler,
        intent_tags=["realtime", "network"],
        latency_class="network",
        requires_network=True,
    )
