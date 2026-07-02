"""工具注册装饰器

提供统一的 register_tool 装饰器，注册时立即生效。
register_external_tool 作为别名保留，兼容旧版第三方插件 API。
"""

from collections.abc import Awaitable, Callable
from typing import Any

from ..runtime.constants import (
    EVIDENCE_KIND_TOOL,
    LATENCY_CLASS_FAST,
)
from .registry import AgentTool, tool_registry


def register_tool(
    name: str,
    description: str,
    parameters: dict[str, Any],
    intent_tags: list[str] | None = None,
    latency_class: str = LATENCY_CLASS_FAST,
    requires_network: bool = False,
    requires_image: bool = False,
    evidence_kind: str = EVIDENCE_KIND_TOOL,
    metadata: dict[str, Any] | None = None,
) -> Callable[
    [Callable[..., Awaitable[str]]], Callable[..., Awaitable[str]]
]:
    """工具注册装饰器（立即生效）

    将异步函数标记为Agent工具并立即注册到 tool_registry。
    内置工具和第三方插件均可使用此装饰器。

    参数:
        name: 工具名称（需全局唯一，同名会覆盖）
        description: 工具描述（供LLM决策使用）
        parameters: JSON Schema参数定义
        intent_tags: 意图标签列表（如 realtime/network/image）
        latency_class: 延迟级别（fast/network/slow）
        requires_network: 是否需要网络
        requires_image: 是否需要图片输入
        evidence_kind: 证据类型（tool/context）
        metadata: 附加元数据

    返回:
        装饰器函数

    使用示例:
        from liuying_plugins.AI.agent.tools import register_tool

        @register_tool(
            name="my_tool",
            description="我的自定义工具",
            parameters={
                "type": "object",
                "properties": {"arg": {"type": "string"}},
                "required": ["arg"],
            },
            intent_tags=["local"],
        )
        async def my_tool(arg: str) -> str:
            return f"result: {arg}"
    """

    def decorator(
        func: Callable[..., Awaitable[str]]
    ) -> Callable[..., Awaitable[str]]:
        """立即注册工具到注册表"""
        tool = AgentTool(
            name=name,
            description=description,
            parameters=parameters,
            func=func,
            intent_tags=intent_tags or [],
            latency_class=latency_class,
            requires_network=requires_network,
            requires_image=requires_image,
            evidence_kind=evidence_kind,
            metadata=metadata or {},
        )
        tool_registry.register(tool)
        return func

    return decorator


# 保留旧名称为别名，兼容现有第三方插件
register_external_tool = register_tool
