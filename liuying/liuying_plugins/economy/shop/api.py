"""商店对外公开 API

提供 register_item 装饰器与 register_items 函数，
其他插件通过这两个接口注册道具模板与对应使用处理器。
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
import random
from typing import ClassVar, TypeAlias

from liuying.models._economy import ItemTemplate
from liuying.utils.enum import PropHandle
from liuying.utils.log import logger
from liuying.utils.manager.priority_manager import PriorityLifecycle
from liuying.utils.user import UserGold

from .defaults import DEFAULT_ITEMS
from .registry import UseResult, registry

_UseFunc: TypeAlias = Callable[[str, dict, int], Awaitable[UseResult]]
_CanUseFunc: TypeAlias = Callable[[str, dict], Awaitable[bool]]


@dataclass(slots=True)
class _PendingItem:
    """待注册道具项

    参数:
        item_id: 道具唯一标识
        name: 道具显示名称
        metadata: 道具模板元数据
        use_func: 使用处理函数，None 表示仅注册模板
        can_use_func: 可选前置检查函数
    """

    item_id: str
    name: str
    metadata: dict = field(default_factory=dict)
    use_func: _UseFunc | None = None
    can_use_func: _CanUseFunc | None = None


class _ItemTemplateRegistry:
    """道具模板注册表（单例）

    收集通过 register_item 装饰器声明的道具，
    在插件启动时统一写入数据库并注册使用处理器。
    """

    _instance: ClassVar["_ItemTemplateRegistry | None"] = None

    def __new__(cls) -> "_ItemTemplateRegistry":
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._pending: list[_PendingItem] = []
            cls._instance = instance
        return cls._instance

    def add(
        self,
        item_id: str,
        name: str,
        metadata: dict,
        use_func: _UseFunc | None = None,
        can_use_func: _CanUseFunc | None = None,
    ) -> None:
        """添加待注册道具

        参数:
            item_id: 道具 ID
            name: 道具名称
            metadata: 模板元数据
            use_func: 使用处理函数
            can_use_func: 前置检查函数
        """
        self._pending.append(
            _PendingItem(
                item_id=item_id,
                name=name,
                metadata=metadata,
                use_func=use_func,
                can_use_func=can_use_func,
            )
        )

    async def flush(self) -> None:
        """将所有待注册道具写入数据库并注册处理器"""
        if not self._pending:
            return

        items = [p.metadata for p in self._pending]
        await ItemTemplate.batch_register(items)

        for pending in self._pending:
            if pending.use_func is not None:
                registry.register(
                    pending.item_id,
                    pending.name,
                    pending.use_func,
                    pending.can_use_func,
                )

        self._pending.clear()


_registry = _ItemTemplateRegistry()


def register_item(
    item_id: str,
    name: str,
    *,
    price: int = 0,
    description: str | None = None,
    item_type: str | None = None,
    image_url: str | None = None,
    name_color: str | None = None,
    description_color: str | None = None,
    limited_time: int = -1,
    discount: int = 100,
    is_visible: int = 1,
    limit_purchase: int = -1,
    shop_name: str = "default",
    can_use_func: _CanUseFunc | None = None,
) -> Callable[[_UseFunc], _UseFunc]:
    """注册商店道具（装饰器）

    一次性声明道具模板与对应使用处理函数，由启动钩子统一写入数据库。

    参数:
        item_id: 道具唯一标识，必填
        name: 道具显示名称，必填
        price: 道具价格，单位金币
        description: 道具描述
        item_type: 道具类型，例如"消耗品""武器"
        image_url: 道具图片 URL 或本地路径
        name_color: 道具名称显示颜色（十六进制）
        description_color: 道具描述显示颜色（十六进制）
        limited_time: 限时销售截止时间戳，-1 表示不限时
        discount: 折扣百分比，100 为原价
        is_visible: 是否在商店可见，0 不可见，1 可见
        limit_purchase: 商店中每人限购数量，-1 表示不限购
        shop_name: 所属商店名称，默认"default"
        can_use_func: 可选前置检查函数

    返回:
        Callable[[_UseFunc], _UseFunc]: 装饰器函数

    示例:
        @register_item(item_id="item_hp_potion", name="生命药水", price=1000)
        async def use_hp_potion(user_id, item_info, quantity=1):
            return UseResult(success=True, ...)
    """

    def decorator(func: _UseFunc) -> _UseFunc:
        metadata = {
            "id": item_id,
            "name": name,
            "price": price,
            "description": description,
            "type": item_type,
            "image_url": image_url,
            "name_color": name_color,
            "description_color": description_color,
            "limited_time": limited_time,
            "discount": discount,
            "is_visible": is_visible,
            "limit_purchase": limit_purchase,
            "shop_name": shop_name,
        }
        _registry.add(
            item_id=item_id,
            name=name,
            metadata=metadata,
            use_func=func,
            can_use_func=can_use_func,
        )
        return func

    return decorator


async def register_items(items: dict | list[dict]) -> tuple[int, int]:
    """注册道具（委托给 ItemTemplate.batch_register）

    参数:
        items: 道具数据，单个字典或字典列表

    返回:
        tuple[int, int]: (成功注册数量, 总数量)
    """
    return await ItemTemplate.batch_register(items)


@registry.item_use("item_gold_coin", "金币袋")
async def _use_gold_coin(
    user_id: str, item_info: dict, quantity: int = 1
) -> UseResult:
    """使用金币袋

    参数:
        user_id: 用户 ID
        item_info: 道具信息字典
        quantity: 使用数量

    返回:
        UseResult: 使用结果
    """
    gold_amount = random.randint(10, 50000) * quantity
    await UserGold.add_user_gold(user_id, gold_amount)
    return UseResult(
        success=True,
        result_type=PropHandle.USE,
        message=f"打开金币袋 x {quantity}，获得 {gold_amount} 金币!",
    )


@PriorityLifecycle.on_startup(priority=2)
async def _init_store_data() -> None:
    """插件启动时初始化商店数据"""
    await _registry.flush()
    await register_items(DEFAULT_ITEMS)
    logger.info("商店道具初始化完成")


__all__ = ["register_item", "register_items"]
