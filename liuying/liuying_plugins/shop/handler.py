"""道具处理器模块"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar

from liuying.utils.enum import PropHandle


@dataclass(slots=True)
class UseResult:
    """道具使用结果

    参数:
        success: 是否成功
        result_type: 结果类型
        message: 结果消息
        data: 附加数据
    """

    success: bool = False
    result_type: PropHandle = PropHandle.FAILED
    message: str = ""
    data: dict = field(default_factory=dict)


class ItemHandler(ABC):
    """道具处理器抽象基类"""

    @property
    @abstractmethod
    def item_id(self) -> str:
        """道具 ID"""

    @property
    @abstractmethod
    def item_name(self) -> str:
        """道具名称"""

    @abstractmethod
    async def use(
        self, user_id: str, item_info: dict, quantity: int = 1, **kwargs
    ) -> UseResult:
        """使用道具

        参数:
            user_id: 用户 ID
            item_info: 道具信息字典
            quantity: 使用数量

        返回:
            UseResult: 使用结果
        """

    async def can_use(self, user_id: str, item_info: dict) -> bool:
        """检查是否可以使用道具

        参数:
            user_id: 用户 ID
            item_info: 道具信息字典

        返回:
            bool: 是否可以使用
        """
        return True


class HandlerRegistry:
    """道具处理器注册表"""

    _handlers: ClassVar[dict[str, ItemHandler]] = {}
    _name_to_id: ClassVar[dict[str, str]] = {}

    @classmethod
    def register(cls, handler: ItemHandler) -> bool:
        """注册道具处理器

        参数:
            handler: 道具处理器实例

        返回:
            bool: 是否注册成功
        """
        if not isinstance(handler, ItemHandler):
            return False
        cls._handlers[handler.item_id] = handler
        cls._name_to_id[handler.item_name] = handler.item_id
        return True

    @classmethod
    def unregister(cls, item_id: str) -> bool:
        """注销道具处理器

        参数:
            item_id: 道具 ID

        返回:
            bool: 是否注销成功
        """
        handler = cls._handlers.pop(item_id, None)
        if not handler:
            return False
        cls._name_to_id.pop(handler.item_name, None)
        return True

    @classmethod
    def get(cls, key: str) -> ItemHandler | None:
        """获取道具处理器（支持 ID 或名称查找）

        参数:
            key: 道具 ID 或名称

        返回:
            ItemHandler | None: 道具处理器实例
        """
        return cls._handlers.get(key) or cls._handlers.get(
            cls._name_to_id.get(key, "")
        )

    @classmethod
    def item_use(
        cls,
        item_id: str,
        item_name: str = "",
        can_use_func: Callable | None = None,
    ) -> Callable:
        """道具使用装饰器

        参数:
            item_id: 道具 ID
            item_name: 道具名称
            can_use_func: 可选的使用前检查函数

        返回:
            装饰器函数
        """

        def decorator(func: Callable) -> Callable:
            handler = _FuncHandler(item_id, item_name or item_id, func, can_use_func)
            cls.register(handler)
            func._item_id = item_id
            return func

        return decorator


class _FuncHandler(ItemHandler):
    """基于函数的道具处理器"""

    __slots__ = ("_can_use_func", "_item_id", "_item_name", "_use_func")

    def __init__(
        self,
        item_id: str,
        item_name: str,
        use_func: Callable,
        can_use_func: Callable | None = None,
    ):
        self._item_id = item_id
        self._item_name = item_name
        self._use_func = use_func
        self._can_use_func = can_use_func

    @property
    def item_id(self) -> str:
        return self._item_id

    @property
    def item_name(self) -> str:
        return self._item_name

    async def use(
        self, user_id: str, item_info: dict, quantity: int = 1, **kwargs
    ) -> UseResult:
        return await self._use_func(user_id, item_info, quantity)

    async def can_use(self, user_id: str, item_info: dict) -> bool:
        if self._can_use_func:
            return await self._can_use_func(user_id, item_info)
        return True


registry = HandlerRegistry()

__all__ = ["HandlerRegistry", "ItemHandler", "UseResult", "registry"]