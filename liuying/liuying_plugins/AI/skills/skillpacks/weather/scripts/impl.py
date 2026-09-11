"""天气查询实现

通过 runtime.llm_helper.web_search 实现免配置天气查询。
"""

from typing import Any

from liuying.liuying_plugins.AI.tools import AgentTool

_MAX_WEATHER_RESULTS = 3
"""天气查询最大结果数"""


async def query_weather(
    city: str,
    llm_helper: Any = None,
) -> str:
    """查询天气

    通过 llm_helper.web_search 查询指定城市天气。

    参数:
        city: 城市名
        llm_helper: LLM助手实例

    返回:
        str: 天气信息文本
    """
    if llm_helper is None:
        return "天气查询不可用：未配置LLM助手"
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
        return f"天气查询失败: {e}"


def build_weather_tool(runtime: Any) -> AgentTool:
    """构建天气查询工具

    参数:
        runtime: SkillRuntime 实例

    返回:
        AgentTool: 天气查询工具
    """
    llm_helper = getattr(runtime, "llm_helper", None)

    async def _handler(city: str) -> str:
        """天气查询handler

        参数:
            city: 城市名

        返回:
            str: 天气信息
        """
        return await query_weather(
            city=city, llm_helper=llm_helper
        )

    return AgentTool(
        name="get_weather",
        description="查询指定城市的天气预报",
        parameters={
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "城市名",
                },
            },
            "required": ["city"],
        },
        func=_handler,
        intent_tags=["realtime", "network"],
        latency_class="network",
        requires_network=True,
    )
