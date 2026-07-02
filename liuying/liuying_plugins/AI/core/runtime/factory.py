"""服务工厂

依赖注入/服务工厂模式实现，统一创建并缓存服务实例，
避免散乱的直接构造与重复实例化。
"""

from collections.abc import Callable
from typing import Any

from liuying.utils.log import logger

__all__ = ["ServiceFactory", "service_factory"]


class ServiceFactory:
    """服务工厂

    通过注册的工厂函数懒创建服务实例并缓存，保证同一名称返回同一实例。
    """

    def __init__(self) -> None:
        """初始化服务工厂"""
        self._factories: dict[str, Callable[..., Any]] = {}
        """已注册的工厂函数 {服务名: 工厂函数}"""
        self._cache: dict[str, Any] = {}
        """已创建的服务实例缓存 {服务名: 实例}"""

    def register_service(
        self, name: str, factory: Callable[..., Any]
    ) -> None:
        """注册服务工厂函数

        参数:
            name: 服务名称
            factory: 工厂函数，调用后返回服务实例
        """
        if not name:
            logger.warning("注册服务失败：名称为空", command="AI")
            return
        self._factories[name] = factory
        self._cache.pop(name, None)
        logger.debug(f"已注册服务工厂: {name}", command="AI")

    def get_service(self, name: str) -> Any:
        """获取服务实例

        命中缓存直接返回，否则调用工厂函数创建并缓存。
        未注册时返回 None。

        参数:
            name: 服务名称

        返回:
            Any: 服务实例，未注册或创建失败时返回 None
        """
        if name in self._cache:
            return self._cache[name]
        factory = self._factories.get(name)
        if factory is None:
            logger.warning(f"服务未注册: {name}", command="AI")
            return None
        try:
            instance = factory()
            self._cache[name] = instance
            return instance
        except Exception as e:
            logger.warning(
                f"创建服务 {name} 失败: {e}",
                command="AI",
                e=e,
            )
            return None

    def unregister_service(self, name: str) -> bool:
        """注销服务工厂并清除缓存

        参数:
            name: 服务名称

        返回:
            bool: 是否成功注销
        """
        if name in self._factories:
            self._factories.pop(name, None)
            self._cache.pop(name, None)
            logger.debug(f"已注销服务: {name}", command="AI")
            return True
        return False

    def clear_cache(self) -> None:
        """清空所有服务实例缓存，保留工厂注册"""
        self._cache.clear()
        logger.debug("服务实例缓存已清空", command="AI")


service_factory = ServiceFactory()
"""服务工厂单例"""
