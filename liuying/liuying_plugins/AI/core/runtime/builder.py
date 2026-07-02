"""运行时配置构建器

以链式API形式化构建运行时配置，覆盖LLM/记忆等核心开关，
未显式设置的项回退到配置文件默认值，供运行时组装或上层调用消费。
"""

from typing import Any

from liuying.utils.log import logger

from ...config import get_config

__all__ = ["RuntimeBuilder", "runtime_builder"]


class RuntimeBuilder:
    """运行时配置构建器

    提供链式API构建运行时配置，build 后返回配置快照。
    未显式设置的项回退到配置文件默认值。
    """

    def __init__(self) -> None:
        """初始化运行时配置构建器"""
        self._config: dict[str, Any] = {}
        """已显式设置的配置项"""

    def with_llm(self, name: str) -> "RuntimeBuilder":
        """指定LLM供应商标识

        参数:
            name: 供应商/模型标识

        返回:
            RuntimeBuilder: 构建器自身，支持链式调用
        """
        self._config["llm"] = name
        return self

    def with_memory(self, enabled: bool) -> "RuntimeBuilder":
        """指定记忆系统是否启用

        参数:
            enabled: 是否启用记忆

        返回:
            RuntimeBuilder: 构建器自身，支持链式调用
        """
        self._config["memory"] = bool(enabled)
        return self

    def _apply_defaults(self, result: dict[str, Any]) -> None:
        """为未显式设置的项填充配置默认值

        参数:
            result: 待补充默认值的配置字典
        """
        if "llm" not in result:
            provider = get_config("CHAT_PROVIDER", None)
            if provider:
                result["llm"] = provider
        if "memory" not in result:
            result["memory"] = bool(get_config("MEMORY_ENABLED", True))

    def build(self) -> dict:
        """构建运行时配置快照

        合并显式设置与配置默认值，返回独立副本，不影响构建器状态。

        返回:
            dict: 运行时配置字典
        """
        result = dict(self._config)
        self._apply_defaults(result)
        logger.debug(
            f"运行时配置构建完成: {len(result)} 项",
            command="AI",
        )
        return result

    def reset(self) -> "RuntimeBuilder":
        """清空已设置的配置项，便于单例复用

        返回:
            RuntimeBuilder: 构建器自身，支持链式调用
        """
        self._config = {}
        return self


runtime_builder = RuntimeBuilder()
"""运行时配置构建器单例"""
