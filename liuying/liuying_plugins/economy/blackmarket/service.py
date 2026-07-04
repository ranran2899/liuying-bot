"""黑市系统商店核心服务模块

提供黑市商品的购买、查询和定时刷新逻辑。
黑市商品由系统随机刷新，价格在原价基础上浮动，
匿名交易，收入进入国库。
"""

import random

from liuying.liuying_plugins.economy.shop.inventory import ItemInventory
from liuying.models._economy import BlackMarketItem, ItemTemplate
from liuying.models.treasury import Treasury
from liuying.utils.log import logger
from liuying.utils.user import UserGold

# 黑市化名列表
_SELLER_ALIASES = [
    "神秘商人",
    "黑市商人",
    "流浪商贩",
    "地下交易者",
    "暗影中介",
]

# 刷新数量范围
REFRESH_MIN_ITEMS = 5
REFRESH_MAX_ITEMS = 10
# 价格浮动范围
PRICE_FLOAT_MIN = 0.8
PRICE_FLOAT_MAX = 1.5
# 单个商品最大库存
MAX_STOCK_PER_ITEM = 5

# 金币库名称
_TREASURY_NAME = "gold_treasury"


class BlackMarketService:
    """黑市系统商店服务类

    处理黑市商品的购买、查询和定时刷新逻辑。
    黑市商品由系统随机刷新，价格在原价基础上浮动，
    匿名交易，收入进入国库。

    参数:
        user_id: 用户ID
    """

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.inventory = ItemInventory(user_id)

    async def buy_item(self, item_keyword: str, quantity: int) -> str:
        """购买黑市商品

        参数:
            item_keyword: 道具名称或ID
            quantity: 购买数量

        返回:
            str: 购买结果消息
        """
        if quantity <= 0:
            return "购买数量必须大于0"

        matches = await BlackMarketItem.find_by_keyword(item_keyword)
        if not matches:
            return f"黑市中没有'{item_keyword}'"

        item = matches[0]
        item_id = item.get("item_id", item.get("id", ""))
        item_name = item.get("name", item_keyword)
        stock = item.get("quantity", 0)
        unit_price = item.get("price", 0)

        if stock < quantity:
            return f"黑市中'{item_name}'库存不足，当前库存：{stock}"

        total_cost = unit_price * quantity
        current_gold = await UserGold.get_user_gold(self.user_id)
        if current_gold < total_cost:
            return (
                f"金币不足! 需要{total_cost:,}金币，"
                f"当前有{current_gold:,}金币"
            )

        reduced = await UserGold.reduce_user_gold(self.user_id, total_cost)
        if not reduced:
            return f"金币不足! 需要{total_cost:,}金币"

        add_ok = await self.inventory.add(item_id, quantity)
        if not add_ok:
            await UserGold.add_user_gold(self.user_id, total_cost)
            return "购买失败，道具入背包失败，金币已返还"

        ok = await BlackMarketItem.reduce_quantity(item_id, quantity)
        if not ok:
            await UserGold.add_user_gold(self.user_id, total_cost)
            return "购买失败，库存减少失败，金币已返还"

        await Treasury.increase_treasury_money(total_cost, _TREASURY_NAME)

        updated_gold = await UserGold.get_user_gold(self.user_id)
        logger.info(
            f"黑市购买: {item_name} x {quantity}, "
            f"花费: {total_cost}, 买家: {self.user_id}",
            "黑市购买",
        )
        return (
            f"购买成功!\n获得{item_name} x {quantity}\n"
            f"花费{total_cost:,}金币\n剩余金币: {updated_gold:,}"
        )

    async def get_all_items(self) -> list[dict]:
        """获取所有黑市商品

        返回:
            list[dict]: 黑市商品字典列表
        """
        return await BlackMarketItem.get_all_items()

    async def search_items(self, keyword: str) -> list[dict]:
        """搜索黑市商品

        参数:
            keyword: 搜索关键字

        返回:
            list[dict]: 匹配的商品字典列表
        """
        return await BlackMarketItem.find_by_keyword(keyword)

    @classmethod
    async def refresh(cls) -> str:
        """刷新黑市商品

        清空现有商品，从道具模板中随机选取若干道具，
        价格在原价基础上浮动，每个商品库存随机，
        收入归国库所有。

        返回:
            str: 刷新结果消息
        """
        cleared = await BlackMarketItem.clear_all()

        templates = await ItemTemplate.filter().all()
        if not templates:
            logger.warning("黑市刷新失败: 没有可用的道具模板", "黑市刷新")
            return "黑市刷新失败，系统中没有可用的道具模板"

        target = min(
            random.randint(REFRESH_MIN_ITEMS, REFRESH_MAX_ITEMS),
            len(templates),
        )
        chosen = random.sample(list(templates), target)

        added = 0
        for template in chosen:
            data = template.get_data()
            item_id = data.get("id", "")
            if not item_id:
                continue
            base_price = int(data.get("price", 0))
            if base_price <= 0:
                base_price = 1
            float_rate = random.uniform(PRICE_FLOAT_MIN, PRICE_FLOAT_MAX)
            price = max(1, int(base_price * float_rate))
            quantity = random.randint(1, MAX_STOCK_PER_ITEM)
            seller_name = random.choice(_SELLER_ALIASES)

            item_data = {
                "name": data.get("name", ""),
                "description": data.get("description", ""),
                "type": data.get("type", ""),
                "image_url": data.get("image_url", ""),
                "name_color": data.get("name_color", ""),
                "description_color": data.get("description_color", ""),
                "price": base_price,
            }
            await BlackMarketItem.add_item(
                item_id=item_id,
                item_data=item_data,
                quantity=quantity,
                price=price,
                seller_name=seller_name,
            )
            added += 1

        logger.info(
            f"黑市刷新完成: 清除{cleared}件旧商品，新增{added}件新商品",
            "黑市刷新",
        )
        return f"黑市已刷新! 本次共上架{added}件商品"
