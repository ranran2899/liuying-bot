"""商店管理服务模块

封装用户商店相关的业务逻辑：开店、上架、下架、改价、热销榜、交易日志。
命令层只负责参数提取与消息构建，业务校验与数据库操作集中于此。
"""

from dataclasses import dataclass

from liuying.models._economy import Shop, ShopItem
from liuying.models._log.shop_log import ShopTransactionLog
from liuying.utils.log import logger

from .inventory import ItemInventory
from .template import TemplateRepository

MAX_SHOP_ITEM_PRICE = 100_000_000
MAX_SHOP_ITEM_QUANTITY = 99
MAX_SHOP_ITEM_TYPES = 10
MAX_SHOP_NAME_LENGTH = 6


def calc_discount(price: int, discount: int) -> int:
    """计算折扣后的价格

    参数:
        price: 原价
        discount: 折扣百分比，100 表示原价

    返回:
        int: 折扣后的价格
    """
    return int(price * discount / 100)


@dataclass(slots=True)
class ListResult:
    """上架/下架/改价操作结果

    参数:
        error: 错误信息，None 表示成功
        item_name: 道具名称
    """

    error: str | None = None
    item_name: str = ""


class ShopService:
    """商店管理服务

    参数:
        user_id: 操作用户 ID
    """

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.inventory = ItemInventory(user_id)

    async def create_shop(self, shop_name: str) -> str | None:
        """创建用户商店

        参数:
            shop_name: 商店名称

        返回:
            str | None: 错误信息，None 表示成功
        """
        if not shop_name:
            return "商店名称不能为空"
        if len(shop_name) > MAX_SHOP_NAME_LENGTH:
            return f"商店名称不能超过{MAX_SHOP_NAME_LENGTH}个字符"
        if await Shop.filter(owner_id=self.user_id).exists():
            return "你已经有商店了，每人只能创建一个"
        if await Shop.filter(shop_name=shop_name).exists():
            return f"商店名称'{shop_name}'已被使用"

        success = await Shop.create_shop(shop_name, self.user_id)
        if not success:
            return "创建商店失败"
        return None

    async def list_item_in_shop(
        self, item_keyword: str, price: int, quantity: int = 1
    ) -> ListResult:
        """在用户商店上架物品

        参数:
            item_keyword: 道具名称或 ID
            price: 出售价格
            quantity: 上架数量

        返回:
            ListResult: 上架结果
        """
        if price < 0:
            return ListResult(error="上架价格不能为负数")
        if price > MAX_SHOP_ITEM_PRICE:
            return ListResult(error=f"上架价格不能超过{MAX_SHOP_ITEM_PRICE:,}金币")
        if quantity <= 0:
            return ListResult(error="上架数量必须大于0")
        if quantity > MAX_SHOP_ITEM_QUANTITY:
            return ListResult(error=f"单次上架数量不能超过{MAX_SHOP_ITEM_QUANTITY}")

        shop = await Shop.get_shop_by_owner(self.user_id)
        if not shop:
            return ListResult(error="你还没有商店，请先使用'开店'命令创建商店")

        inv_item = await self.inventory.resolve_inventory_item(item_keyword)
        if not inv_item:
            return ListResult(error=f"背包中没有'{item_keyword}'这个道具")

        item_id = inv_item["id"]
        shop_items = await ShopItem.get_shop_items(shop["shop_name"])
        already_listed = any(i.get("id") == item_id for i in shop_items)
        if not already_listed and len(shop_items) >= MAX_SHOP_ITEM_TYPES:
            return ListResult(
                error=f"你的商店上架物品种类已达上限({MAX_SHOP_ITEM_TYPES}种)"
            )

        available = inv_item.get("count", 0)
        if available < quantity:
            return ListResult(
                error=f"{inv_item['name']}数量不足，当前拥有：{available}"
            )

        item_name = inv_item.get("name", item_keyword)
        await self.inventory.reduce(item_id, quantity)

        item_data = {
            key: inv_item.get(key, "")
            for key in (
                "name",
                "description",
                "type",
                "image_url",
                "name_color",
                "description_color",
            )
        }

        success = await ShopItem.add_item(
            shop_name=shop["shop_name"],
            item_id=item_id,
            quantity=quantity,
            price=price,
            seller_id=self.user_id,
            item_data=item_data,
        )
        if not success:
            await self.inventory.add(item_id, quantity)
            return ListResult(error="上架失败，物品已返还背包")

        return ListResult(item_name=item_name)

    async def delist_item(self, item_keyword: str, quantity: int = 1) -> ListResult:
        """从商店下架物品，归还背包

        参数:
            item_keyword: 道具名称或 ID
            quantity: 下架数量

        返回:
            ListResult: 下架结果
        """
        if quantity <= 0:
            return ListResult(error="下架数量必须大于0")

        shop = await Shop.get_shop_by_owner(self.user_id)
        if not shop:
            return ListResult(error="你还没有商店")

        shop_item = await ShopItem.find_item_by_keyword(
            shop["shop_name"], item_keyword
        )
        if not shop_item:
            return ListResult(error=f"商店中没有'{item_keyword}'这个道具")

        item_id = shop_item.get("id", "")
        item_name = shop_item.get("name", item_keyword)
        delist_qty = min(quantity, shop_item["quantity"])

        delisted = await ShopItem.delist_item(shop["shop_name"], item_id, delist_qty)
        if delisted <= 0:
            return ListResult(error="下架失败")

        await self.inventory.add(item_id, delisted)
        return ListResult(item_name=item_name)

    async def change_price(self, item_keyword: str, new_price: int) -> ListResult:
        """修改商店物品价格

        参数:
            item_keyword: 道具名称或 ID
            new_price: 新价格

        返回:
            ListResult: 修改结果
        """
        if new_price < 0:
            return ListResult(error="价格不能为负数")
        if new_price > MAX_SHOP_ITEM_PRICE:
            return ListResult(error=f"价格不能超过{MAX_SHOP_ITEM_PRICE:,}金币")

        shop = await Shop.get_shop_by_owner(self.user_id)
        if not shop:
            return ListResult(error="你还没有商店")

        shop_item = await ShopItem.find_item_by_keyword(
            shop["shop_name"], item_keyword
        )
        if not shop_item:
            return ListResult(error=f"商店中没有'{item_keyword}'这个道具")

        item_id = shop_item.get("id", "")
        item_name = shop_item.get("name", item_keyword)

        success = await ShopItem.update_price(shop["shop_name"], item_id, new_price)
        if not success:
            return ListResult(error="修改价格失败")

        return ListResult(item_name=item_name)

    async def get_my_shop(self) -> dict | None:
        """获取用户自己的商店信息和物品列表

        返回:
            dict | None: 商店信息字典
        """
        shop = await Shop.get_shop_by_owner(self.user_id)
        if not shop:
            return None
        shop_items = await ShopItem.get_shop_items(shop["shop_name"])
        return {**shop, "items": shop_items}

    @staticmethod
    async def get_hot_items(limit: int = 10) -> list[dict]:
        """获取热销道具排行榜

        参数:
            limit: 返回数量上限

        返回:
            list[dict]: 热销道具列表
        """
        return await TemplateRepository.get_hot_items(limit)

    @staticmethod
    async def record_purchase_history(
        user_id: str,
        item_id: str,
        item_name: str,
        quantity: int,
        price: int,
        source: str,
        target_shop: str = "",
    ) -> bool:
        """记录购买历史到交易日志

        参数:
            user_id: 用户 ID
            item_id: 道具 ID
            item_name: 道具名称
            quantity: 购买数量
            price: 单价
            source: 来源(shop/auction)
            target_shop: 目标商店名称

        返回:
            bool: 是否记录成功
        """
        success = await ShopTransactionLog.record_transaction(
            user_id=user_id,
            item_id=item_id,
            item_name=item_name,
            quantity=quantity,
            price=price,
            source=source,
            target_shop=target_shop,
        )
        if not success:
            logger.warning(f"记录交易日志失败: {user_id} {item_id}")
        return success


__all__ = ["ListResult", "ShopService", "calc_discount"]
