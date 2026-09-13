"""本体插件智能模式函数工具桥接

遍历已加载插件在 ``__plugin_meta__.extra.smart_tools`` 中声明的
AICallableTag（见 liuying.configs.utils.models），转换为 AgentTool
注册进工具注册表，使 Agent 能直接调用第三方插件暴露的智能模式函数。

规则：
- 同名工具跳过注册（保护内置工具与先注册方）
- func 为同步函数时自动放入线程池执行，避免阻塞事件循环
- extra 经序列化丢失 func 的声明跳过并记录日志
"""

import asyncio
from collections.abc import Callable
import inspect
from typing import Any

import nonebot

from liuying.configs.utils.models import AICallableParam, AICallableTag
from liuying.utils.log import logger

from .registry import AgentTool, tool_registry


class SmartToolBridge:
    """本体插件智能模式函数工具桥接器

    将插件声明的 AICallableTag 批量转换为 AgentTool 注册进
    tool_registry，供 Agent 循环直接调用。
    """

    def register_all(self) -> int:
        """注册所有插件声明的智能模式函数工具

        遍历已加载插件的 metadata.extra.smart_tools，
        应在插件元数据全部加载后的启动钩子中调用。

        返回:
            int: 成功注册的工具数
        """
        count = 0
        for plugin in nonebot.get_loaded_plugins():
            metadata = plugin.metadata
            if not (metadata and metadata.extra):
                continue
            for tag in metadata.extra.get("smart_tools") or []:
                count += self._register_tag(tag, plugin.name)
        return count

    def _register_tag(self, tag: Any, plugin_name: str) -> int:
        """注册单个智能工具声明

        参数:
            tag: AICallableTag 实例或序列化后的字典
            plugin_name: 来源插件名（用于日志与溯源）

        返回:
            int: 注册成功返回1，跳过返回0
        """
        if isinstance(tag, dict):
            tag = AICallableTag(**tag)
        if not isinstance(tag, AICallableTag):
            return 0
        if tag.func is None:
            logger.debug(
                f"智能工具 {tag.name} 缺少func（可能被序列化），"
                f"跳过注册（来源插件: {plugin_name}）",
                command="AI",
            )
            return 0
        if tool_registry.get(tag.name) is not None:
            logger.warning(
                f"智能工具 {tag.name} 与已有工具同名，"
                f"跳过注册（来源插件: {plugin_name}）",
                command="AI",
            )
            return 0
        merged_metadata = {**tag.metadata, "source": f"plugin:{plugin_name}"}
        tool_registry.register(
            AgentTool(
                name=tag.name,
                description=tag.description,
                parameters=self._convert_parameters(tag.parameters),
                func=self._wrap_handler(tag.name, tag.func),
                intent_tags=tag.intent_tags,
                latency_class=tag.latency_class,
                requires_network=tag.requires_network,
                requires_image=tag.requires_image,
                evidence_kind=tag.evidence_kind,
                metadata=merged_metadata,
            )
        )
        logger.debug(
            f"已注册插件智能工具 {tag.name}（来源插件: {plugin_name}）",
            command="AI",
        )
        return 1

    @staticmethod
    def _convert_parameters(
        param: AICallableParam | None,
    ) -> dict[str, Any]:
        """将AICallableParam转换为JSON Schema参数定义

        参数:
            param: 本体声明的参数模型，None时返回空参数

        返回:
            dict: JSON Schema字典
        """
        if param is None:
            return {"type": "object", "properties": {}, "required": []}
        return {
            "type": param.type or "object",
            "properties": {
                name: {"type": prop.type, "description": prop.description}
                for name, prop in (param.properties or {}).items()
            },
            "required": list(param.required or []),
        }

    @staticmethod
    def _wrap_handler(
        tag_name: str, func: Callable[..., Any]
    ) -> Callable[..., Any]:
        """包装smart_tools函数为AgentTool执行约定

        统一为异步调用并保证返回字符串；同步函数放入线程池执行。

        参数:
            tag_name: 工具名（用于生成handler名便于排查）
            func: 插件声明的原始函数

        返回:
            Callable: 异步handler，签名 (**kwargs) -> str
        """

        async def _handler(**kwargs) -> str:
            if inspect.iscoroutinefunction(func):
                result = await func(**kwargs)
            else:
                result = await asyncio.to_thread(func, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            return "" if result is None else str(result)

        _handler.__name__ = f"smart_tool_{tag_name}"
        return _handler


smart_tool_bridge = SmartToolBridge()
"""智能模式函数工具桥接器单例"""
