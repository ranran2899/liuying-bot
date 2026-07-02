"""Wiki查询技能

通过联网搜索提供Wiki百科查询能力。
"""

from liuying.utils.log import logger

from ...core.llm import llm_helper

_MAX_WIKI_RESULTS = 3
"""Wiki查询最大结果数"""


async def search_wiki(query: str) -> str:
    """查询Wiki百科

    通过 llm_helper.web_search 查询Wiki百科条目。

    参数:
        query: 查询关键词

    返回:
        str: Wiki摘要文本
    """
    if not query or not query.strip():
        return "请提供查询关键词"
    keyword = f"{query.strip()} wiki 百科"
    try:
        results = await llm_helper.web_search(
            keyword, count=_MAX_WIKI_RESULTS
        )
        if not results:
            return f"未查询到 {query} 的Wiki信息"
        lines: list[str] = [f"{query} Wiki:"]
        for item in results:
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            url = item.get("url", "")
            if title:
                lines.append(f"- {title}")
            if snippet:
                lines.append(f"  {snippet}")
            if url:
                lines.append(f"  URL: {url}")
        return "\n".join(lines)
    except Exception as e:
        logger.warning(
            f"Wiki查询失败: {e}", command="AI", e=e
        )
        return f"Wiki查询失败: {e}"
