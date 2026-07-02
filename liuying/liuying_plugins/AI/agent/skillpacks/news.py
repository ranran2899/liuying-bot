"""新闻查询技能

通过联网搜索提供新闻查询能力。
"""

from liuying.utils.log import logger

from ...core.llm import llm_helper

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


async def get_news(category: str = "general") -> str:
    """查询新闻

    通过 llm_helper.web_search 按分类查询最新新闻。

    参数:
        category: 新闻分类，默认 general

    返回:
        str: 新闻摘要文本
    """
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
        logger.warning(
            f"新闻查询失败: {e}", command="AI", e=e
        )
        return f"新闻查询失败: {e}"
