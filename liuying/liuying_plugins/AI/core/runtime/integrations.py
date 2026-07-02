"""外部系统集成管理

提供统一的外部系统集成注册与调用接口，
将WebUI等局外系统的接入收敛到一处，解耦核心运行时。
"""

import inspect
from typing import Any

from liuying.utils.log import logger

__all__ = ["IntegrationManager", "integration_manager"]


class IntegrationManager:
    """外部系统集成管理器

    注册并管理局外系统集成处理器，支持同步/异步处理器的统一调用。
    """

    def __init__(self) -> None:
        """初始化集成管理器"""
        self._handlers: dict[str, Any] = {}
        """已注册的集成处理器 {名称: 处理器}"""

    def register(self, name: str, handler: Any) -> None:
        """注册集成处理器

        参数:
            name: 集成名称（如 webui）
            handler: 处理器实例或可调用对象
        """
        if not name:
            logger.warning("注册集成失败：名称为空", command="AI")
            return
        self._handlers[name] = handler
        logger.info(f"已注册集成: {name}", command="AI")

    def get(self, name: str) -> Any | None:
        """获取集成处理器

        参数:
            name: 集成名称

        返回:
            Any | None: 处理器实例，未注册时返回 None
        """
        return self._handlers.get(name)

    async def call(self, name: str, *args: Any) -> Any:
        """调用集成处理器

        自动适配同步与异步处理器，未注册时返回 None。

        参数:
            name: 集成名称
            *args: 透传给处理器的位置参数

        返回:
            Any: 处理器返回值，未注册或异常时返回 None
        """
        handler = self._handlers.get(name)
        if handler is None:
            logger.warning(f"集成未注册: {name}", command="AI")
            return None
        try:
            result = handler(*args)
            if inspect.isawaitable(result):
                result = await result
            return result
        except Exception as e:
            logger.warning(
                f"调用集成 {name} 失败: {e}",
                command="AI",
                e=e,
            )
            return None

    def unregister(self, name: str) -> bool:
        """注销集成处理器

        参数:
            name: 集成名称

        返回:
            bool: 是否成功注销
        """
        if name in self._handlers:
            self._handlers.pop(name, None)
            logger.info(f"已注销集成: {name}", command="AI")
            return True
        return False

    def list_names(self) -> list[str]:
        """列出已注册的集成名称

        返回:
            list[str]: 集成名称列表
        """
        return list(self._handlers.keys())


integration_manager = IntegrationManager()
"""外部系统集成管理器单例"""
