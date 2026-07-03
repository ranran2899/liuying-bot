"""委托求购板核心服务模块

提供求购单的发布、出售、取消、搜索等核心业务逻辑，
求购单创建时预扣金币，取消或过期时退还冻结金币。
"""

from liuying.liuying_plugins.economy.shop.inventory import ItemInventory
from liuying.models._economy import CommissionOrder, ItemTemplate
from liuying.utils.log import logger
from liuying.utils.user import UserGold

MAX_USER_ORDER_TYPES = 5
MAX_ITEM_QUANTITY = 99
MAX_ITEM_PRICE = 1_000_000
COMMISSION_EXPIRE_DAYS = 3

_ITEM_DATA_KEYS = (
    "name",
    "description",
    "type",
    "image_url",
    "name_color",
    "description_color",
)


def _match_keyword(item: dict, keyword: str) -> bool:
    """检查物品是否匹配关键字（精确ID/名称或模糊名称匹配）

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


class CommissionService:
    """委托求购板核心服务类

    处理求购单的所有业务逻辑，包括发布求购、出售道具、
    取消求购和搜索求购单。求购单创建时预扣金币，
    取消或过期时退还冻结金币。
    """

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.inventory = ItemInventory(user_id)

    async def place_order(
        self, item_keyword: str, unit_price: int, quantity: int
    ) -> str:
        """发布求购单

        先从背包查找道具模板，检查价格和数量上限，
        预扣金币后创建求购单。同一买家对同一道具的求购单
        累加数量并更新价格。

        参数:
            item_keyword: 道具名称或ID
            unit_price: 求购单价
            quantity: 求购数量

        返回:
            str: 结果消息
        """
        if unit_price <= 0:
            return "求购单价必须大于0"
        if unit_price > MAX_ITEM_PRICE:
            return f"求购单价不能超过{MAX_ITEM_PRICE:,}金币"
        if quantity <= 0:
            return "求购数量必须大于0"
        if quantity > MAX_ITEM_QUANTITY:
            return f"单次求购数量不能超过{MAX_ITEM_QUANTITY}"

        inv_item = await self.inventory.resolve_inventory_item(
            item_keyword
        )
        if not inv_item:
            return f"背包中没有'{item_keyword}'这个道具"

        item_id = inv_item["id"]
        template = await ItemTemplate.get_template_by_id(item_id)
        if not template:
            return (
                f"道具'{inv_item.get('name', item_id)}'"
                f"未在系统中注册，无法求购"
            )

        existing = await CommissionOrder._find_by_buyer_and_item(
            self.user_id, item_id
        )
        if not existing:
            user_orders = await CommissionOrder.get_user_orders(
                self.user_id
            )
            if len(user_orders) >= MAX_USER_ORDER_TYPES:
                return (
                    f"你已有{len(user_orders)}个求购单，"
                    f"上限为{MAX_USER_ORDER_TYPES}个"
                )

        gold_diff = self._calc_gold_diff(
            existing, unit_price, quantity
        )

        if gold_diff > 0:
            current_gold = await UserGold.get_user_gold(self.user_id)
            if current_gold < gold_diff:
                return (
                    f"金币不足! 需要{gold_diff:,}金币，"
                    f"当前有{current_gold:,}金币"
                )
            await UserGold.reduce_user_gold(
                self.user_id, gold_diff, source="求购冻结"
            )
        elif gold_diff < 0:
            await UserGold.add_user_gold(
                self.user_id, -gold_diff, source="求购调整退还"
            )

        item_data = {
            key: inv_item.get(key, "") for key in _ITEM_DATA_KEYS
        }

        success = await CommissionOrder.add_order(
            buyer_id=self.user_id,
            item_id=item_id,
            quantity=quantity,
            unit_price=unit_price,
            item_data=item_data,
            expire_days=COMMISSION_EXPIRE_DAYS,
        )

        if not success:
            if gold_diff > 0:
                await UserGold.add_user_gold(
                    self.user_id, gold_diff, source="求购失败退还"
                )
            return "求购单创建失败"

        item_name = inv_item.get("name", item_keyword)
        logger.info(
            f"求购单创建: {item_name} x {quantity}, "
            f"单价: {unit_price}, 买家: {self.user_id}",
            "求购单创建",
        )

        if gold_diff > 0:
            gold_msg = f"已冻结{gold_diff:,}金币"
        elif gold_diff < 0:
            gold_msg = f"已退还{-gold_diff:,}金币"
        else:
            gold_msg = "金币无变化"

        return (
            f"求购成功!\n已发布{item_name} x {quantity}的求购单，"
            f"单价{unit_price:,}金币/个\n{gold_msg}"
        )

    @staticmethod
    def _calc_gold_diff(
        existing: CommissionOrder | None,
        new_price: int,
        add_quantity: int,
    ) -> int:
        """计算发布求购单时的金币差额

        参数:
            existing: 已存在的求购单
            new_price: 新单价
            add_quantity: 新增数量

        返回:
            int: 需要额外扣除的金币（正数扣除，负数退还）
        """
        if not existing:
            return new_price * add_quantity

        old_remaining = (
            existing.quantity - existing.fulfilled_quantity
        )
        old_frozen = existing.unit_price * old_remaining
        new_remaining = old_remaining + add_quantity
        new_frozen = new_price * new_remaining
        return new_frozen - old_frozen

    async def fulfill_order(
        self, item_keyword: str, quantity: int
    ) -> str:
        """向求购单出售道具

        先从自己背包找道具，然后查找最高单价的求购单（排除自己的），
        检查自己背包数量足够，减少道具，获得金币。

        参数:
            item_keyword: 道具名称或ID
            quantity: 出售数量

        返回:
            str: 结果消息
        """
        if quantity <= 0:
            return "出售数量必须大于0"

        inv_item = await self.inventory.resolve_inventory_item(
            item_keyword
        )
        if not inv_item:
            return f"背包中没有'{item_keyword}'这个道具"

        item_id = inv_item["id"]
        item_name = inv_item.get("name", item_keyword)
        available = inv_item.get("count", 0)

        if available < quantity:
            return f"{item_name}数量不足，当前拥有：{available}"

        active_orders = await CommissionOrder.get_active_orders()
        matching = [
            o
            for o in active_orders
            if o.get("item_id") == item_id
            and o.get("buyer_id") != self.user_id
        ]
        if not matching:
            return f"没有找到{item_name}的求购单"

        matching.sort(
            key=lambda x: x.get("unit_price", 0), reverse=True
        )

        plan = self._build_fulfill_plan(matching, quantity)
        if not plan:
            return "没有可满足的求购单"

        total_sold = sum(qty for _, qty in plan)
        total_gold = sum(
            o.get("unit_price", 0) * qty for o, qty in plan
        )

        await self.inventory.reduce(item_id, total_sold)

        for order, qty in plan:
            buyer_id = order.get("buyer_id", "")
            unit_price = order.get("unit_price", 0)
            await UserGold.add_user_gold(
                self.user_id,
                unit_price * qty,
                source="求购出售",
            )
            await CommissionOrder.fulfill(buyer_id, item_id, qty)

        logger.info(
            f"求购出售: {item_name} x {total_sold}, "
            f"获得: {total_gold}, 卖家: {self.user_id}",
            "求购出售",
        )

        if total_sold < quantity:
            return (
                f"出售成功!\n已出售{item_name} x {total_sold}"
                f"(请求{quantity}，求购单不足)\n"
                f"获得{total_gold:,}金币"
            )
        return (
            f"出售成功!\n已出售{item_name} x {total_sold}\n"
            f"获得{total_gold:,}金币"
        )

    @staticmethod
    def _build_fulfill_plan(
        orders: list[dict], quantity: int
    ) -> list[tuple[dict, int]]:
        """构建出售计划，从最高价开始分配出售数量

        参数:
            orders: 按单价降序排列的求购单列表
            quantity: 需要出售的总数量

        返回:
            list[tuple[dict, int]]: (求购单, 出售数量) 的列表
        """
        plan: list[tuple[dict, int]] = []
        remaining = quantity

        for order in orders:
            if remaining <= 0:
                break
            order_remaining = order.get("quantity", 0) - order.get(
                "fulfilled_quantity", 0
            )
            fulfill_qty = min(order_remaining, remaining)
            if fulfill_qty > 0:
                plan.append((order, fulfill_qty))
                remaining -= fulfill_qty

        return plan

    async def cancel_order(
        self, item_keyword: str, quantity: int
    ) -> str:
        """取消自己的求购单，退还冻结金币

        参数:
            item_keyword: 道具名称或ID
            quantity: 取消数量

        返回:
            str: 结果消息
        """
        if quantity <= 0:
            return "取消数量必须大于0"

        user_orders = await CommissionOrder.get_user_orders(
            self.user_id
        )
        matched = [
            o for o in user_orders if _match_keyword(o, item_keyword)
        ]
        if not matched:
            return f"你没有发布'{item_keyword}'的求购单"

        order = matched[0]
        item_id = order.get("item_id", order.get("id", ""))
        item_name = order.get("name", item_keyword)
        unit_price = order.get("unit_price", 0)

        cancel_qty, _ = await CommissionOrder.cancel_order(
            self.user_id, item_id, quantity
        )
        if cancel_qty <= 0:
            return "取消失败，可能求购单已被全部满足"

        refund = unit_price * cancel_qty
        if refund > 0:
            await UserGold.add_user_gold(
                self.user_id, refund, source="求购取消退还"
            )

        logger.info(
            f"求购单取消: {item_name} x {cancel_qty}, "
            f"买家: {self.user_id}",
            "求购单取消",
        )
        return (
            f"取消成功!\n已取消{item_name} x {cancel_qty}的求购单，"
            f"退还{refund:,}金币"
        )

    async def get_my_orders(self) -> list[dict]:
        """获取自己的求购单

        返回:
            list[dict]: 求购单字典列表
        """
        return await CommissionOrder.get_user_orders(self.user_id)

    async def get_all_orders(self) -> list[dict]:
        """获取所有活跃求购单

        返回:
            list[dict]: 活跃求购单字典列表
        """
        return await CommissionOrder.get_active_orders()

    async def search_orders(self, keyword: str) -> list[dict]:
        """搜索求购单

        参数:
            keyword: 搜索关键字

        返回:
            list[dict]: 匹配的求购单字典列表
        """
        return await CommissionOrder.find_by_keyword(keyword)

    @classmethod
    async def expire_orders(cls) -> int:
        """过期处理，退还冻结金币

        返回:
            int: 处理的过期求购单数量
        """
        expired = await CommissionOrder.expire_orders()
        if not expired:
            return 0

        count = 0
        for order in expired:
            remaining = order.quantity - order.fulfilled_quantity
            refund = order.unit_price * remaining
            if refund > 0:
                await UserGold.add_user_gold(
                    order.buyer_id, refund, source="求购过期退还"
                )
            await order.delete()
            count += 1

        logger.info(
            f"求购单过期处理: 共处理{count}个过期求购单",
            "求购单过期处理",
        )
        return count
