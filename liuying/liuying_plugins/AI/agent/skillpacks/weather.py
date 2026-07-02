"""天气查询技能

通过联网搜索提供天气查询能力。
"""

from liuying.utils.log import logger

from ...core.llm import llm_helper

_MAX_WEATHER_RESULTS = 3
"""天气查询最大结果数"""


async def get_weather(city: str) -> str:
    """查询天气

    通过 llm_helper.web_search 查询指定城市天气。

    参数:
        city: 城市名

    返回:
        str: 天气信息文本
    """
    if not city or not city.strip():
        return "请提供城市名"
    city = city.strip()
    keyword = f"{city} 天气预报 今天"
    try:
        results = await llm_helper.web_search(
            keyword, count=_MAX_WEATHER_RESULTS
        )
        if not results:
            return f"未查询到 {city} 的天气信息"
        lines: list[str] = [f"{city}天气:"]
        for item in results:
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            if title:
                lines.append(f"- {title}")
            if snippet:
                lines.append(f"  {snippet}")
        return "\n".join(lines)
    except Exception as e:
        logger.warning(
            f"天气查询失败: {e}", command="AI", e=e
        )
        return f"天气查询失败: {e}"
