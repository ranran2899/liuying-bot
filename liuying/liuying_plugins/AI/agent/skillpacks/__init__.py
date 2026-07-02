"""内置技能包集合

提供新闻、天气、日期时间、Wiki、游戏信息等查询技能。
每个技能通过 llm_helper.web_search 实现免配置查询。
"""

from ..runtime.constants import (
    INTENT_TAG_LOCAL,
    INTENT_TAG_NETWORK,
    INTENT_TAG_REALTIME,
    LATENCY_CLASS_FAST,
    LATENCY_CLASS_NETWORK,
)
from ..tools import AgentTool
from .datetime_tool import get_current_time
from .game_info import get_game_info
from .news import get_news
from .weather import get_weather
from .wiki import search_wiki

__all__ = [
    "get_current_time",
    "get_game_info",
    "get_news",
    "get_weather",
    "register_builtin_skillpacks",
    "search_wiki",
]


async def _async_get_current_time(
    timezone: str = "Asia/Shanghai",
) -> str:
    """获取当前日期时间（异步包装）

    参数:
        timezone: 时区名

    返回:
        str: 格式化的当前时间描述
    """
    return get_current_time(timezone)


def register_builtin_skillpacks(registry) -> int:
    """注册内置单文件技能包到工具注册表

    将 news/weather/datetime/wiki/game_info 5 个内置技能
    注册为 AgentTool，供 Agent 工具调用使用。

    参数:
        registry: ToolRegistry 实例

    返回:
        int: 注册成功的工具数量
    """
    tools: list[AgentTool] = [
        AgentTool(
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
            func=get_news,
            intent_tags=[INTENT_TAG_REALTIME, INTENT_TAG_NETWORK],
            latency_class=LATENCY_CLASS_NETWORK,
            requires_network=True,
        ),
        AgentTool(
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
            func=get_weather,
            intent_tags=[INTENT_TAG_REALTIME, INTENT_TAG_NETWORK],
            latency_class=LATENCY_CLASS_NETWORK,
            requires_network=True,
        ),
        AgentTool(
            name="get_current_time",
            description="获取当前日期时间（支持时区）",
            parameters={
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "时区名，默认 Asia/Shanghai",
                        "default": "Asia/Shanghai",
                    },
                },
                "required": [],
            },
            func=_async_get_current_time,
            intent_tags=[INTENT_TAG_LOCAL],
            latency_class=LATENCY_CLASS_FAST,
        ),
        AgentTool(
            name="search_wiki",
            description="查询Wiki百科条目",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "查询关键词",
                    },
                },
                "required": ["query"],
            },
            func=search_wiki,
            intent_tags=[INTENT_TAG_NETWORK],
            latency_class=LATENCY_CLASS_NETWORK,
            requires_network=True,
        ),
        AgentTool(
            name="get_game_info",
            description="查询游戏信息（攻略/介绍）",
            parameters={
                "type": "object",
                "properties": {
                    "game": {
                        "type": "string",
                        "description": "游戏名",
                    },
                },
                "required": ["game"],
            },
            func=get_game_info,
            intent_tags=[INTENT_TAG_NETWORK],
            latency_class=LATENCY_CLASS_NETWORK,
            requires_network=True,
        ),
    ]

    registered = 0
    for tool in tools:
        try:
            registry.register(tool)
            registered += 1
        except Exception:
            pass
    return registered
