"""道具使用处理器注册表

管理道具使用函数的注册与查找，基于函数签名而非抽象基类，
降低调用方复杂度。通过装饰器注册的函数将被存入注册表，
使用道具时按 ID 或名称查找对应处理器并调用。

函数签名约定：
    async def use_func(user_id: str, item_info: dict, quantity: int = 1) -> UseResult
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import ClassVar, TypeAlias

from liuying.utils.enum import PropHandle

_UseFunc: TypeAlias = Callable[[str, dict, int], Awaitable["UseResult"]]
_CanUseFunc: TypeAlias = Callable[[str, dict], Awaitable[bool]]


@dataclass(slots=True)
class UseResult:
    """道具使用结果

    参数:
        success: 是否成功
        result_type: 结果类型，默认为 PropHandle.FAILED
        message: 结果消息
        data: 附加数据
    """

    success: bool = False
    result_type: PropHandle = PropHandle.FAILED
    message: str = ""
    data: dict = field(default_factory=dict)


@dataclass(slots=True)
class _HandlerEntry:
    """道具处理器内部条目

    参数:
        item_id: 道具唯一标识
        item_name: 道具显示名称
        use_func: 使用处理函数
        can_use_func: 可选前置检查函数
    """

    item_id: str
    item_name: str
    use_func: _UseFunc
    can_use_func: _CanUseFunc | None = None


class HandlerRegistry:
    """道具处理器注册表（单例）

    通过 item_use 装饰器注册异步使用函数，使用 ID 或名称查找。
    单例模式隔离可变状态，避免多实例数据污染。
    """

    _instance: ClassVar["HandlerRegistry | None"] = None

    def __new__(cls) -> "HandlerRegistry":
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._handlers: dict[str, _HandlerEntry] = {}
            instance._name_to_id: dict[str, str] = {}
            cls._instance = instance
        return cls._instance

    @classmethod
    def instance(cls) -> "HandlerRegistry":
        """获取注册表单例"""
        return cls()

    def register(
        self,
        item_id: str,
        item_name: str,
        use_func: _UseFunc,
        can_use_func: _CanUseFunc | None = None,
    ) -> None:
        """注册道具使用处理器

        参数:
            item_id: 道具唯一标识
            item_name: 道具显示名称
            use_func: 使用处理函数
            can_use_func: 可选前置检查函数
        """
        entry = _HandlerEntry(
            item_id=item_id,
            item_name=item_name or item_id,
            use_func=use_func,
            can_use_func=can_use_func,
        )
        self._handlers[item_id] = entry
        self._name_to_id[entry.item_name] = item_id

    def unregister(self, item_id: str) -> bool:
        """注销道具处理器

        参数:
            item_id: 道具 ID

        返回:
            bool: 是否注销成功
        """
        entry = self._handlers.pop(item_id, None)
        if entry is None:
            return False
        self._name_to_id.pop(entry.item_name, None)
        return True

    def get(self, key: str) -> _HandlerEntry | None:
        """获取道具处理器（支持 ID 或名称查找）

        参数:
            key: 道具 ID 或名称

        返回:
            _HandlerEntry | None: 处理器条目，未找到返回 None
        """
        entry = self._handlers.get(key)
        if entry is not None:
            return entry
        target_id = self._name_to_id.get(key)
        return self._handlers.get(target_id) if target_id else None

    def item_use(
        self,
        item_id: str,
        item_name: str = "",
        can_use_func: _CanUseFunc | None = None,
    ) -> Callable[[_UseFunc], _UseFunc]:
        """道具使用装饰器

        参数:
            item_id: 道具唯一标识
            item_name: 道具显示名称，为空时使用 item_id
            can_use_func: 可选前置检查函数

        返回:
            Callable[[_UseFunc], _UseFunc]: 装饰器函数

        示例:
            @registry.item_use("item_gold_coin", "金币袋")
            async def use_gold_coin(user_id, item_info, quantity=1):
                ...
        """

        def decorator(func: _UseFunc) -> _UseFunc:
            self.register(item_id, item_name, func, can_use_func)
            return func

        return decorator


registry = HandlerRegistry()

__all__ = ["HandlerRegistry", "UseResult", "registry"]
