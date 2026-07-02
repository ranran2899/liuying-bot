"""Agent 工具系统

提供工具注册表、装饰器和内置工具集。
内置工具在导入时通过 @register_tool 装饰器自动注册。
"""

from .builtin import (  # noqa: F401  触发内置工具注册
    context,
    group,
    knowledge,
    media,
    memory_tools,
    search,
)
from .decorators import register_external_tool, register_tool
from .registry import AgentTool, ToolRegistry, tool_registry

__all__ = [
    "AgentTool",
    "ToolRegistry",
    "register_external_tool",
    "register_tool",
    "tool_registry",
]
