"""运行时组件组装

按配置动态组装运行时核心组件（LLM/记忆/情绪/上下文），
统一暴露给上层调用，避免散乱的直接导入与重复初始化判断。
"""

from typing import Any

from liuying.utils.log import logger

from ...config import get_config
from ..context import context_manager
from ..emotion import emotion_manager
from ..llm import llm_helper
from ..memory import memory_manager

__all__ = ["RuntimeAssembly", "runtime_assembly"]


_COMPONENT_PROVIDERS: dict[str, tuple[str, Any]] = {
    "llm": ("ENABLE_AI", llm_helper),
    "memory": ("MEMORY_ENABLED", memory_manager),
    "emotion": ("EMOTION_ENABLED", emotion_manager),
    "context": ("", context_manager),
}
"""组件名 -> (配置键, 组件实例) 映射

配置键为空串表示该组件始终启用（无独立开关）。
"""


class RuntimeAssembly:
    """运行时组件组装器

    按配置动态组装运行时核心组件，统一管理组件实例的启用状态。
    首次调用 assemble 后缓存结果，后续读取走缓存。
    """

    def __init__(self) -> None:
        """初始化运行时组件组装器"""
        self._components: dict[str, Any] = {}
        """已组装的组件实例字典"""
        self._assembled = False
        """是否已完成组装"""

    def _is_enabled(self, config_key: str) -> bool:
        """根据配置键判断组件是否启用

        参数:
            config_key: 配置键名，空串表示始终启用

        返回:
            bool: 是否启用
        """
        if not config_key:
            return True
        return bool(get_config(config_key, True))

    def assemble(self) -> dict:
        """按配置组装运行时组件

        遍历组件提供者，依据各自配置开关决定是否纳入运行时。
        已组装时直接返回缓存结果。

        返回:
            dict: {组件名: 组件实例}
        """
        if self._assembled:
            return dict(self._components)

        self._components = {}
        for name, (config_key, instance) in _COMPONENT_PROVIDERS.items():
            if not self._is_enabled(config_key):
                logger.debug(
                    f"组件 {name} 已被配置关闭，跳过组装",
                    command="AI",
                )
                continue
            self._components[name] = instance

        self._assembled = True
        logger.info(
            f"运行时组件组装完成: {len(self._components)} 项",
            command="AI",
        )
        return dict(self._components)

    def get_component(self, name: str) -> Any | None:
        """按名称获取已组装的组件

        未组装时自动触发一次组装。

        参数:
            name: 组件名（llm/memory/emotion/context）

        返回:
            Any | None: 组件实例，未启用或不存在时返回 None
        """
        if not self._assembled:
            self.assemble()
        return self._components.get(name)

    def reset(self) -> None:
        """重置组装状态，强制下次重新组装"""
        self._components = {}
        self._assembled = False
        logger.debug("运行时组件组装状态已重置", command="AI")


runtime_assembly = RuntimeAssembly()
"""运行时组件组装器单例"""
