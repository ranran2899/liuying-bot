"""工具注册中心

定义 AgentTool 数据结构和 ToolRegistry 注册中心。
注册时自动归类到 tool_catalog。
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from ..runtime.constants import (
    EVIDENCE_KIND_TOOL,
    LATENCY_CLASS_FAST,
)
from ..runtime.tool_catalog import tool_catalog


@dataclass(slots=True)
class AgentTool:
    """工具定义

    参考参考插件 AgentTool 设计。

    Attributes:
        name: 工具名（唯一键）
        description: 工具描述（供LLM决策使用）
        parameters: JSON Schema参数定义
        func: 工具执行函数（异步）
        is_disabled: 是否禁用
        intent_tags: 意图标签列表
        latency_class: 延迟级别（fast/network/slow）
        requires_network: 是否需要网络
        requires_image: 是否需要图片输入
        evidence_kind: 证据类型（tool/context）
        metadata: 附加元信息
    """

    name: str
    description: str
    parameters: dict[str, Any]
    func: Callable[..., Awaitable[str]]
    is_disabled: bool = False
    intent_tags: list[str] = field(default_factory=list)
    latency_class: str = LATENCY_CLASS_FAST
    requires_network: bool = False
    requires_image: bool = False
    evidence_kind: str = EVIDENCE_KIND_TOOL
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_metadata(self) -> dict[str, Any]:
        """导出元数据字典

        返回:
            dict: 元数据字典
        """
        return {
            "intent_tags": list(self.intent_tags),
            "latency_class": self.latency_class,
            "requires_network": self.requires_network,
            "requires_image": self.requires_image,
            "evidence_kind": self.evidence_kind,
            "description": self.description,
            **self.metadata,
        }


class ToolRegistry:
    """工具注册中心

    提供 register/get/active/list_names 方法。
    注册时自动归类到 tool_catalog。
    保持薄注册层设计，不处理限流/重试/配额。
    revision 随注册变化递增，供下游（如 planner）做缓存失效判断。
    """

    def __init__(self) -> None:
        """初始化工具注册表"""
        self._tools: dict[str, AgentTool] = {}
        self.revision: int = 0

    def register(self, tool: AgentTool) -> None:
        """注册工具（同名覆盖）

        注册时自动调用 tool_catalog.categorize_by_metadata
        将工具归类到对应分类。

        参数:
            tool: 工具实例
        """
        self._tools[tool.name] = tool
        self.revision += 1
        tool_catalog.categorize_by_metadata(
            tool.name, tool.to_metadata()
        )

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

    def list_names(self) -> list[str]:
        """列出所有工具名

        返回:
            list[str]: 工具名列表
        """
        return list(self._tools.keys())


tool_registry = ToolRegistry()
"""工具注册表单例"""
