"""拍卖行核心服务模块

提供拍卖行的上架、购买、搜索、分页等核心业务逻辑，
通过统一交易服务聚合展示拍卖行和个人商店的物品。
"""

from dataclasses import dataclass

from liuying.configs.config import Config
from liuying.liuying_plugins.economy.shop.inventory import ItemInventory
from liuying.liuying_plugins.economy.shop.template import TemplateRepository
from liuying.liuying_plugins.economy.trading import VenueAggregator, VenueItem
from liuying.models._economy import AuctionItem, AuctionTransaction
from liuying.models.treasury import Treasury
from liuying.utils.log import logger
from liuying.utils.user import UserGold

MAX_USER_LISTED_TYPES = 5
MAX_ITEM_QUANTITY = 99
MAX_ITEM_PRICE = 1_000_000
PAGE_SIZE = 20
MAX_SEARCH_RESULTS = 20

# 道具信息保留字段（从道具字典/背包数据中提取的元数据键）
_ITEM_DATA_KEYS: tuple[str, ...] = (
    "name",
    "description",
    "type",
    "rarity",
    "image_url",
)

_PLUGIN_MODULE = "auction"


def _get_fee_rate() -> float:
    """获取交易手续费率

    返回:
        float: 手续费率
    """
    return Config.get_config(_PLUGIN_MODULE, "AUCTION_FEE_RATE", 0.05)


def _get_expire_days() -> int:
    """获取拍卖到期天数

    返回:
        int: 到期天数
    """
    return Config.get_config(_PLUGIN_MODULE, "AUCTION_EXPIRE_DAYS", 7)


def _get_max_expire_days() -> int:
    """获取最大到期天数

    返回:
        int: 最大到期天数
    """
    return Config.get_config(_PLUGIN_MODULE, "AUCTION_MAX_EXPIRE_DAYS", 30)


@dataclass(slots=True)
class ListResult:
    """上架操作结果

    参数:
        error: 错误信息，None表示成功
        item_name: 道具名称
    """

    error: str | None = None
    item_name: str = ""


@dataclass(slots=True)
class BuyResult:
    """购买操作结果

    参数:
        success: 是否成功
        message: 结果消息
    """

    success: bool = False
    message: str = ""


@dataclass(slots=True)
class DelistResult:
    """下架操作结果

    参数:
        success: 是否成功
        message: 结果消息
    """

    success: bool = False
    message: str = ""


@dataclass(slots=True)
class ChangePriceResult:
    """改价操作结果

    参数:
        success: 是否成功
        message: 结果消息
    """

    success: bool = False
    message: str = ""


def _sort_by_price_desc(items: list[dict]) -> list[dict]:
    """按价格降序排列物品列表

    参数:
        items: 物品列表

    返回:
        list[dict]: 排序后的列表
    """
    items.sort(key=lambda x: x.get("price", 0), reverse=True)
    return items


def _sort_by_price_asc(items: list[dict]) -> list[dict]:
    """按价格升序排列物品列表

    参数:
        items: 物品列表

    返回:
        list[dict]: 排序后的列表
    """
    items.sort(key=lambda x: x.get("price", 0))
    return items


class AuctionService:
    """拍卖行核心服务类

    处理拍卖行的所有业务逻辑，包括物品上架、购买、搜索和分页浏览。
    所有业务方法均为静态方法，直接接收 user_id 参数。
    """

    @staticmethod
    def _match_keyword(item: dict, keyword: str) -> bool:
        """检查物品是否匹配关键字（精确 ID/名称或模糊名称匹配）

        兼容 id 与 item_id 两种字段命名。

        参数:
            item: 物品信息字典
            keyword: 搜索关键字

        返回:
            bool: 是否匹配
        """
        item_id = item.get("id", "") or item.get("item_id", "")
        item_name = item.get("name", "")
        return (
            keyword == item_id
            or keyword == item_name
            or keyword in item_name
        )

    @staticmethod
    async def list_item(
        user_id: str,
        item_keyword: str,
        price: int,
        quantity: int = 1,
        expire_days: int | None = None,
    ) -> ListResult:
        """在拍卖行上架物品

        参数:
            user_id: 用户 ID
            item_keyword: 道具名称或ID
            price: 上架单价
            quantity: 上架数量
            expire_days: 到期天数，None时使用配置默认值

        返回:
            ListResult: 上架结果
        """
        if price <= 0:
            return ListResult(error="上架价格必须大于0")
        if price > MAX_ITEM_PRICE:
            return ListResult(error=f"上架价格不能超过{MAX_ITEM_PRICE:,}金币")
        if quantity <= 0:
            return ListResult(error="上架数量必须大于0")
        if quantity > MAX_ITEM_QUANTITY:
            return ListResult(error=f"单次上架数量不能超过{MAX_ITEM_QUANTITY}")

        max_expire = _get_max_expire_days()
        if expire_days is not None:
            if expire_days <= 0 or expire_days > max_expire:
                return ListResult(
                    error=f"到期天数必须在1-{max_expire}之间"
                )
        else:
            expire_days = _get_expire_days()

        inv_item = await ItemInventory.resolve_item(user_id, item_keyword)
        if not inv_item:
            return ListResult(error=f"背包中没有'{item_keyword}'这个道具")

        available = inv_item.get("count", 0)
        if available < quantity:
            return ListResult(
                error=f"{inv_item['name']}数量不足，当前拥有：{available}"
            )

        item_id = inv_item["id"]

        template = await TemplateRepository.get_by_id(item_id)
        if not template:
            return ListResult(
                error=f"道具'{inv_item.get('name', item_id)}'未在系统中注册，无法上架"
            )

        existing = await AuctionItem._find_by_seller_and_item(user_id, item_id)
        if not existing:
            listed_types = await AuctionItem.get_user_listed_types(user_id)
            if listed_types >= MAX_USER_LISTED_TYPES:
                return ListResult(
                    error=f"你已在拍卖行上架了{listed_types}种物品，"
                    f"上限为{MAX_USER_LISTED_TYPES}种"
                )

        await ItemInventory.reduce(user_id, item_id, quantity)

        item_data = {key: inv_item.get(key, "") for key in _ITEM_DATA_KEYS}

        success = await AuctionItem.add_item(
            seller_id=user_id,
            item_id=item_id,
            quantity=quantity,
            price=price,
            item_data=item_data,
            expire_days=expire_days,
        )
        if not success:
            await ItemInventory.add(user_id, item_id, quantity)
            return ListResult(error="上架失败，物品已返还背包")

        item_name = inv_item.get("name", item_keyword)
        logger.info(
            f"拍卖行上架: {item_name} x {quantity}, "
            f"单价: {price}, 卖家: {user_id}",
            "拍卖行上架",
        )
        return ListResult(item_name=item_name)

    @staticmethod
    async def buy_item(
        user_id: str, item_keyword: str, quantity: int = 1
    ) -> BuyResult:
        """从拍卖行购买物品，自动从价格最低的上架记录开始购买

        参数:
            user_id: 用户 ID
            item_keyword: 道具名称或ID
            quantity: 购买数量

        返回:
            BuyResult: 购买结果
        """
        if quantity <= 0:
            return BuyResult(message="购买数量必须大于0")

        listings = await VenueAggregator.find_venue_items(item_keyword)
        if not listings:
            return BuyResult(message=f"拍卖行中没有'{item_keyword}'")

        listings.sort(key=lambda x: x.price)

        other_listings = [
            item for item in listings if item.seller_id != user_id
        ]
        if not other_listings:
            return BuyResult(message="不能购买自己上架的物品")

        total_available = sum(item.quantity for item in other_listings)
        if total_available < quantity:
            item_name = other_listings[0].name
            return BuyResult(
                message=f"拍卖行中'{item_name}'可购买数量不足，"
                f"当前可购总量：{total_available}"
            )

        purchase_plan = AuctionService._build_purchase_plan(
            other_listings, quantity
        )
        if not purchase_plan:
            return BuyResult(message="可购买数量不足")

        total_cost = sum(listing.price * qty for listing, qty in purchase_plan)
        fee_rate = _get_fee_rate()
        fee = int(total_cost * fee_rate)
        total_payment = total_cost + fee

        current_gold = await UserGold.get_user_gold(user_id)
        if current_gold < total_payment:
            return BuyResult(
                message=f"金币不足! 需要{total_payment:,}金币"
                f"(含手续费{fee:,})，当前有{current_gold:,}金币"
            )

        await UserGold.reduce_user_gold(user_id, total_payment)

        try:
            item_name = await AuctionService._execute_purchase(
                user_id, purchase_plan, fee_rate
            )
        except Exception as e:
            await UserGold.add_user_gold(
                user_id, total_payment, source="拍卖行购买失败退还"
            )
            logger.error(f"拍卖行购买执行失败，已退还金币: {e}", "拍卖行购买")
            return BuyResult(message="购买过程中发生错误，金币已退还")

        await Treasury.increase_treasury_money(fee, "gold_treasury")

        updated_gold = await UserGold.get_user_gold(user_id)
        logger.info(
            f"拍卖行购买: {item_name} x {quantity}, "
            f"花费: {total_payment}(含手续费{fee}), "
            f"买家: {user_id}",
            "拍卖行购买",
        )
        return BuyResult(
            success=True,
            message=(
                f"购买成功!\n获得{item_name} x {quantity}\n"
                f"花费{total_payment:,}金币"
                f"(含手续费{fee:,})\n剩余金币: {updated_gold:,}"
            ),
        )

    @staticmethod
    def _build_purchase_plan(
        listings: list[VenueItem], quantity: int
    ) -> list[tuple[VenueItem, int]]:
        """构建购买计划，从最低价开始分配购买数量

        参数:
            listings: 按价格升序排列的物品列表（不含自己的上架）
            quantity: 需要购买的总数量

        返回:
            list[tuple[VenueItem, int]]: (上架记录, 购买数量) 的列表
        """
        plan: list[tuple[VenueItem, int]] = []
        remaining = quantity

        for listing in listings:
            if remaining <= 0:
                break
            buy_qty = min(listing.quantity, remaining)
            plan.append((listing, buy_qty))
            remaining -= buy_qty

        return plan if remaining <= 0 else []

    @staticmethod
    async def _execute_purchase(
        user_id: str,
        purchase_plan: list[tuple[VenueItem, int]],
        fee_rate: float = 0.0,
    ) -> str:
        """执行购买计划，处理金币转移、库存变动和交易记录

        参数:
            user_id: 买家用户 ID
            purchase_plan: 购买计划列表
            fee_rate: 手续费率

        返回:
            str: 购买的物品名称
        """
        item_name = ""
        for listing, buy_qty in purchase_plan:
            seller_id = listing.seller_id
            unit_price = listing.price
            item_id = listing.id
            item_name = listing.name
            subtotal = unit_price * buy_qty
            fee = int(subtotal * fee_rate)

            await UserGold.add_user_gold(
                seller_id, subtotal, source="拍卖行出售"
            )
            await ItemInventory.add(seller_id, item_id, buy_qty)

            await VenueAggregator.reduce_venue_quantity(listing, buy_qty)

            await AuctionTransaction.record_transaction(
                buyer_id=user_id,
                seller_id=seller_id,
                item_id=item_id,
                item_name=item_name,
                quantity=buy_qty,
                unit_price=unit_price,
                fee=fee,
            )

        return item_name

    @staticmethod
    async def delist_item(
        user_id: str, item_keyword: str, quantity: int = 1
    ) -> DelistResult:
        """下架拍卖行物品，归还背包

        参数:
            user_id: 用户 ID
            item_keyword: 道具名称或ID
            quantity: 下架数量

        返回:
            DelistResult: 下架结果
        """
        if quantity <= 0:
            return DelistResult(message="下架数量必须大于0")

        auction_items = await AuctionItem.get_user_items(user_id)
        matched = [
            item
            for item in auction_items
            if AuctionService._match_keyword(item, item_keyword)
        ]
        if not matched:
            return DelistResult(message=f"你在拍卖行没有上架'{item_keyword}'")

        item = matched[0]
        item_id = item.get("item_id", item.get("id", ""))
        item_name = item.get("name", item_keyword)

        delist_qty, _item_data = await AuctionItem.delist_item(
            user_id, item_id, quantity
        )
        if delist_qty <= 0:
            return DelistResult(message="下架失败")

        await ItemInventory.add(user_id, item_id, delist_qty)

        logger.info(
            f"拍卖行下架: {item_name} x {delist_qty}, "
            f"卖家: {user_id}",
            "拍卖行下架",
        )
        return DelistResult(
            success=True,
            message=f"下架成功! 已将{item_name} x {delist_qty}归还背包",
        )

    @staticmethod
    async def change_price(
        user_id: str, item_keyword: str, new_price: int
    ) -> ChangePriceResult:
        """修改拍卖行上架价格

        参数:
            user_id: 用户 ID
            item_keyword: 道具名称或ID
            new_price: 新单价

        返回:
            ChangePriceResult: 改价结果
        """
        if new_price <= 0:
            return ChangePriceResult(message="价格必须大于0")
        if new_price > MAX_ITEM_PRICE:
            return ChangePriceResult(
                message=f"价格不能超过{MAX_ITEM_PRICE:,}金币"
            )

        auction_items = await AuctionItem.get_user_items(user_id)
        matched = [
            item
            for item in auction_items
            if AuctionService._match_keyword(item, item_keyword)
        ]
        if not matched:
            return ChangePriceResult(
                message=f"你在拍卖行没有上架'{item_keyword}'"
            )

        item = matched[0]
        item_id = item.get("item_id", item.get("id", ""))
        item_name = item.get("name", item_keyword)
        old_price = item.get("price", 0)

        success = await AuctionItem.change_price(user_id, item_id, new_price)
        if not success:
            return ChangePriceResult(message="改价失败")

        logger.info(
            f"拍卖行改价: {item_name}, "
            f"{old_price} -> {new_price}, 卖家: {user_id}",
            "拍卖行改价",
        )
        return ChangePriceResult(
            success=True,
            message=f"改价成功! {item_name}的价格"
            f"已从{old_price:,}改为{new_price:,}金币",
        )

    @staticmethod
    async def get_my_auctions(user_id: str) -> list[dict]:
        """获取用户在拍卖行的上架物品列表

        参数:
            user_id: 用户 ID

        返回:
            list[dict]: 上架物品字典列表
        """
        return await AuctionItem.get_user_items(user_id)

    @staticmethod
    async def get_transaction_history(
        user_id: str, limit: int = 20
    ) -> list[dict]:
        """获取用户交易记录（购买+出售），按时间降序排列

        参数:
            user_id: 用户 ID
            limit: 返回条数上限

        返回:
            list[dict]: 交易记录列表
        """
        buy_records = await AuctionTransaction.get_user_buy_history(
            user_id, limit
        )
        sell_records = await AuctionTransaction.get_user_sell_history(
            user_id, limit
        )
        for record in buy_records:
            record["type"] = "buy"
        for record in sell_records:
            record["type"] = "sell"
        all_records = buy_records + sell_records
        all_records.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return all_records[:limit]

    @staticmethod
    async def compare_prices(item_keyword: str) -> list[dict]:
        """跨店比价，搜索拍卖行和所有个人商店中同一物品的报价

        参数:
            item_keyword: 道具名称或ID

        返回:
            list[dict]: 按价格升序排列的物品列表
        """
        items = await VenueAggregator.find_venue_items(item_keyword)
        all_items = [item.to_dict() for item in items]
        return _sort_by_price_asc(all_items)

    @staticmethod
    async def get_all_listings() -> list[dict]:
        """获取拍卖行所有物品（含商店同步），按价格降序排列

        返回:
            list[dict]: 所有上架物品列表
        """
        items = await VenueAggregator.get_all_venue_items()
        all_items = [item.to_dict() for item in items]
        return _sort_by_price_desc(all_items)

    @staticmethod
    async def search_items(keyword: str) -> list[dict]:
        """搜索拍卖行物品（模糊匹配名称或ID），按价格降序排列

        参数:
            keyword: 搜索关键字

        返回:
            list[dict]: 匹配的物品列表，最多返回MAX_SEARCH_RESULTS条
        """
        items = await VenueAggregator.find_venue_items(keyword)
        all_items = [item.to_dict() for item in items]
        all_items = _sort_by_price_desc(all_items)
        return all_items[:MAX_SEARCH_RESULTS]

    @staticmethod
    async def get_items_page(
        page: int = 1, keyword: str | None = None
    ) -> tuple[list[dict], int, int]:
        """分页获取拍卖行物品，按价格降序排列

        参数:
            page: 页码，从1开始
            keyword: 可选的物品名称过滤关键字

        返回:
            tuple[list[dict], int, int]: (当前页物品列表, 总页数, 当前页码)
        """
        all_items = (
            await AuctionService.search_items(keyword)
            if keyword
            else await AuctionService.get_all_listings()
        )

        total_items = len(all_items)
        total_pages = max(1, (total_items + PAGE_SIZE - 1) // PAGE_SIZE)

        if page < 1 or page > total_pages:
            return [], total_pages, page

        start = (page - 1) * PAGE_SIZE
        return all_items[start : start + PAGE_SIZE], total_pages, page

    @staticmethod
    async def expire_auctions() -> int:
        """处理到期下架，归还物品给卖家

        返回:
            int: 处理的到期物品数量
        """
        expired = await AuctionItem.expire_items()
        if not expired:
            return 0

        count = 0
        for item in expired:
            await ItemInventory.add(item.seller_id, item.item_id, item.quantity)
            await item.delete()
            count += 1

        logger.info(
            f"拍卖行到期下架: 共处理{count}件到期物品", "拍卖行到期下架"
        )
        return count
