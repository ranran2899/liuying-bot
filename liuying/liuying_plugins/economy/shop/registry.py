"""商店道具注册表

集中管理道具模板注册、使用处理器注册。
外部插件通过本模块统一访问商店核心功能。

提供的功能：
    - register_items: 批量注册道具模板到数据库（支持单个和批量）
    - register: 装饰器，同时注册道具模板和使用处理器
    - item_use: 装饰器，仅注册道具使用处理器
    - UseResult: 道具使用结果数据类
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TypeAlias

from liuying.utils.enum import PropHandle
from liuying.utils.log import logger

from .template import TemplateRepository

_UseFunc: TypeAlias = Callable[[str, dict, int], Awaitable["UseResult"]]
_CanUseFunc: TypeAlias = Callable[[str, dict], Awaitable[bool]]
_HandlerEntry: TypeAlias = tuple[_UseFunc, _CanUseFunc | None, str]


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


# === 道具使用处理器注册 ===

# 处理器注册表：item_id -> (use_func, can_use_func, item_name)
_handlers: dict[str, _HandlerEntry] = {}
# 名称到 ID 的映射
_name_to_id: dict[str, str] = {}


def register_handler(
    item_id: str,
    item_name: str,
    use_func: _UseFunc,
    can_use_func: _CanUseFunc | None = None,
) -> None:
    """注册道具使用处理器

    参数:
        item_id: 道具唯一标识
        item_name: 道具显示名称，为空时使用 item_id
        use_func: 使用处理函数
        can_use_func: 可选前置检查函数
    """
    name = item_name or item_id
    _handlers[item_id] = (use_func, can_use_func, name)
    _name_to_id[name] = item_id


def unregister_handler(item_id: str) -> bool:
    """注销道具处理器

    参数:
        item_id: 道具 ID

    返回:
        bool: 是否注销成功
    """
    entry = _handlers.pop(item_id, None)
    if entry is None:
        return False
    _name_to_id.pop(entry[2], None)
    return True


def get_handler(key: str) -> _HandlerEntry | None:
    """获取道具处理器（支持 ID 或名称查找）

    参数:
        key: 道具 ID 或名称

    返回:
        _HandlerEntry | None: 处理器条目，未找到返回 None
    """
    entry = _handlers.get(key)
    if entry is not None:
        return entry
    target_id = _name_to_id.get(key)
    return _handlers.get(target_id) if target_id else None


def item_use(
    item_id: str,
    item_name: str = "",
    can_use_func: _CanUseFunc | None = None,
) -> Callable[[_UseFunc], _UseFunc]:
    """道具使用处理器装饰器

    仅注册使用处理器，不注册道具模板。
    适用于道具模板已通过 register_items 或 defaults.py 注册的场景。

    参数:
        item_id: 道具唯一标识
        item_name: 道具显示名称，为空时使用 item_id
        can_use_func: 可选前置检查函数

    返回:
        Callable[[_UseFunc], _UseFunc]: 装饰器函数

    示例:
        @item_use("item_gold_coin", "金币袋")
        async def use_gold_coin(user_id, item_info, quantity=1):
            ...
    """

    def decorator(func: _UseFunc) -> _UseFunc:
        register_handler(item_id, item_name, func, can_use_func)
        return func

    return decorator


# === 道具模板注册 ===


async def register_items(items: dict | list[dict]) -> tuple[int, int]:
    """批量注册道具模板（支持单个和批量）

    传入单个字典时自动包装为列表处理，无需单独的单道具注册方法。

    参数:
        items: 道具数据，单个字典或字典列表

    返回:
        tuple[int, int]: (成功注册数量, 总数量)
    """
    return await TemplateRepository.batch_register(items)


# === 道具+处理器一体化注册（装饰器）===

# 待注册道具模板列表（装饰器在模块加载时执行，模板数据延迟到启动时写入数据库）
_pending_templates: list[dict] = []


def register(
    name: str,
    item_id: str,
    description: str = "",
    item_type: str = "",
    rarity: int = 1,
    image_url: str = "",
    is_visible: int = 1,
    price: int = 0,
    discount: int = 100,
    limit_purchase: int = -1,
    limited_time: int = -1,
    can_use_func: _CanUseFunc | None = None,
) -> Callable[[_UseFunc], _UseFunc]:
    """注册道具的装饰器

    同时注册道具模板和使用处理器。道具模板延迟到启动时写入数据库

    参数:
        name: 道具名称
        item_id: 道具唯一标识
        description: 道具描述
        item_type: 道具类型
        rarity: 稀有度等级（1-5）
        image_url: 道具图标 URL
        is_visible: 是否可见（1 可见，0 不可见）
        price: 价格
        discount: 折扣（100 表示原价）
        limit_purchase: 限购数量（-1 表示不限购）
        limited_time: 限时时间戳（-1 表示不限时）
        can_use_func: 可选前置检查函数

    返回:
        Callable[[_UseFunc], _UseFunc]: 装饰器函数

    示例:
        @register("金币袋", "item_gold_coin", description="打开获得金币", rarity=2)
        async def use_gold_coin(user_id, item_info, quantity=1):
            ...
    """

    def decorator(func: _UseFunc) -> _UseFunc:
        _pending_templates.append(
            {
                "name": name,
                "id": item_id,
                "description": description,
                "type": item_type,
                "rarity": rarity,
                "image_url": image_url,
                "is_visible": is_visible,
                "price": price,
                "discount": discount,
                "limit_purchase": limit_purchase,
                "limited_time": limited_time,
            }
        )
        register_handler(item_id, name, func, can_use_func)
        return func

    return decorator


async def flush_templates() -> int:
    """将待注册的道具模板写入数据库

    在插件启动时调用，将装饰器收集的道具模板批量写入数据库。
    避免装饰器在模块加载时执行异步数据库操作。

    返回:
        int: 成功注册数量
    """
    if not _pending_templates:
        return 0
    added, total = await TemplateRepository.batch_register(_pending_templates)
    _pending_templates.clear()
    logger.info(f"装饰器注册道具模板完成: {added}/{total}")
    return added

__all__ = [
    "UseResult",
    "flush_templates",
    "get_handler",
    "item_use",
    "register",
    "register_handler",
    "register_items",
    "unregister_handler",
]
