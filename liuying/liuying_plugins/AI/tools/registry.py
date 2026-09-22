"""工具注册中心

定义 AgentTool 数据结构和 ToolRegistry 注册中心。
AgentTool 承载 JSON Schema 参数与异步执行函数，并可导出为
OpenAI function-calling 格式，供统一 ReAct 循环调用。
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AgentTool:
    """工具定义

    承载 JSON Schema 参数与异步执行函数，并可导出为
    OpenAI function-calling 格式，供统一 ReAct 循环调用。

    Attributes:
        name: 工具名（唯一键）
        description: 工具描述（供LLM决策使用）
        parameters: JSON Schema参数定义
        func: 工具执行函数（异步）
        is_disabled: 是否禁用
        metadata: 附加元信息
    """

    name: str
    """工具名（唯一键）"""
    description: str
    """工具描述（供LLM决策使用）"""
    parameters: dict[str, Any]
    """JSON Schema参数定义"""
    func: Callable[..., Awaitable[str]]
    """工具执行函数（异步）"""
    is_disabled: bool = False
    """是否禁用"""
    metadata: dict[str, Any] = field(default_factory=dict)
    """附加元信息"""

    def to_openai_tool(self) -> dict[str, Any]:
        """导出为 OpenAI function-calling 工具定义

        返回:
            dict[str, Any]: 符合 OpenAI tools 数组元素格式的定义
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
                or {"type": "object", "properties": {}},
            },
        }


class ToolRegistry:
    """工具注册中心

    提供 register/get/active/openai_tools 能力。
    保持薄注册层设计，不处理限流/重试/配额/编排。
    """

    def __init__(self) -> None:
        """初始化工具注册表"""
        self._tools: dict[str, AgentTool] = {}

    def register(self, tool: AgentTool) -> None:
        """注册工具（同名覆盖）

        参数:
            tool: 工具实例
        """
        self._tools[tool.name] = tool

    def get(self, name: str) -> AgentTool | None:
        """获取工具

        参数:
            name: 工具名

        返回:
            AgentTool | None: 工具实例或None
        """
        return self._tools.get(name)

    def active_tools(self) -> list[AgentTool]:
        """获取所有未禁用工具

        返回:
            list[AgentTool]: 活动工具列表
        """
        return [t for t in self._tools.values() if not t.is_disabled]

    def openai_tools(self) -> list[dict[str, Any]]:
        """导出全部活动工具的 OpenAI 格式定义

        返回:
            list[dict[str, Any]]: tools 数组，供原生 function-calling 使用
        """
        return [t.to_openai_tool() for t in self.active_tools()]

    def list_names(self) -> list[str]:
        """列出所有工具名

        返回:
            list[str]: 工具名列表
        """
        return list(self._tools.keys())


tool_registry = ToolRegistry()
"""工具注册表单例"""
