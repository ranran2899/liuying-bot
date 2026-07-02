"""Agent循环与工具系统

提供工具注册表、Agent核心循环、技能包加载与内置技能包，
支持LLM自主调用工具完成多步任务。
"""

from .runner import AgentResult, run_agent
from .skill_loader import SkillLoader, skill_loader
from .skillpacks import (
    get_current_time,
    get_game_info,
    get_news,
    get_weather,
    search_wiki,
)
from .tools import AgentTool, ToolRegistry, tool_registry

__all__ = [
    "AgentResult",
    "AgentTool",
    "SkillLoader",
    "ToolRegistry",
    "get_current_time",
    "get_game_info",
    "get_news",
    "get_weather",
    "run_agent",
    "search_wiki",
    "skill_loader",
    "tool_registry",
]
