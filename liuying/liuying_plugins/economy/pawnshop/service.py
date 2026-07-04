"""典当行核心服务模块

提供典当行的典当、赎回、当票查询等核心业务逻辑，
抵押道具借出金币，到期赎回需还本付息。
"""

from datetime import datetime

from liuying.configs.config import Config
from liuying.liuying_plugins.economy.shop.inventory import ItemInventory
from liuying.models._economy import ItemTemplate, PawnTicket
from liuying.utils.log import logger
from liuying.utils.user import UserGold

# 典当折扣率（道具原价的60%作为估价）
PAWN_DISCOUNT_RATE = 0.6
# 默认利率（10%）
DEFAULT_INTEREST_RATE = 0.1
# 道具默认估价基准（无price字段时使用）
DEFAULT_ITEM_PRICE = 100
# 单次最大典当数量
MAX_PAWN_QUANTITY = 99

# 道具信息保留字段（从道具字典/背包数据中提取的元数据键）
_ITEM_DATA_KEYS: tuple[str, ...] = (
    "name",
    "description",
    "type",
    "image_url",
    "name_color",
    "description_color",
)

_PLUGIN_MODULE = "pawnshop"

# 当票状态
_STATUS_ACTIVE = "active"
_STATUS_REDEEMED = "redeemed"
_STATUS_FORECLOSED = "foreclosed"

# 历史当票状态集合
_HISTORY_STATUSES = (_STATUS_REDEEMED, _STATUS_FORECLOSED)


def _get_redeem_days() -> int:
    """获取赎回期限天数

    返回:
        int: 赎回期限天数
    """
    return Config.get_config(_PLUGIN_MODULE, "PAWN_REDEEM_DAYS", 7)


class PawnshopService:
    """典当行核心服务类

    处理典当行的所有业务逻辑，包括道具典当、赎回、
    当票查询和逾期处理。典当时按道具估价借出金币，
    赎回时需归还本金并支付利息。
    """

    def __init__(self, user_id: str):
        """初始化典当行服务

        参数:
            user_id: 用户ID
        """
        self.user_id = user_id
        self.inventory = ItemInventory(user_id)

    async def pawn_item(
        self, item_keyword: str, quantity: int = 1
    ) -> str:
        """典当道具，抵押道具借出金币

        估价逻辑：道具原价 * 典当折扣率（60%），
        无price字段时按默认估价100计算。
        借款金额 = 单件估价 * 数量。

        参数:
            item_keyword: 道具名称或ID
            quantity: 典当数量，默认1

        返回:
            str: 操作结果消息
        """
        if quantity <= 0:
            return "典当数量必须大于0"
        if quantity > MAX_PAWN_QUANTITY:
            return f"单次典当数量不能超过{MAX_PAWN_QUANTITY}"

        inv_item = await self.inventory.resolve_inventory_item(item_keyword)
        if not inv_item:
            return f"背包中没有'{item_keyword}'这个道具"

        available = inv_item.get("count", 0)
        if available < quantity:
            item_name = inv_item.get("name", item_keyword)
            return f"{item_name}数量不足，当前拥有：{available}"

        item_id = inv_item["id"]
        item_name = inv_item.get("name", item_keyword)

        template = await ItemTemplate.get_template_by_id(item_id)
        if not template:
            return f"道具'{item_name}'未在系统中注册，无法典当"

        unit_price = inv_item.get("price") or DEFAULT_ITEM_PRICE
        unit_loan = int(unit_price * PAWN_DISCOUNT_RATE)
        total_loan = unit_loan * quantity

        await self.inventory.reduce(item_id, quantity)

        item_data = {key: inv_item.get(key, "") for key in _ITEM_DATA_KEYS}

        try:
            await PawnTicket.create_ticket(
                user_id=self.user_id,
                item_id=item_id,
                quantity=quantity,
                loan_amount=total_loan,
                interest_rate=DEFAULT_INTEREST_RATE,
                item_data=item_data,
                redeem_days=_get_redeem_days(),
            )
        except Exception as e:
            await self.inventory.add(item_id, quantity)
            logger.error(
                f"典当行创建当票失败: {e}", "典当行典当"
            )
            return "典当失败，道具已返还背包"

        await UserGold.add_user_gold(
            self.user_id, total_loan, source="典当行借款"
        )

        redeem_amount = int(total_loan * (1 + DEFAULT_INTEREST_RATE))
        logger.info(
            f"典当行典当: {item_name} x {quantity}, "
            f"借款: {total_loan}, 用户: {self.user_id}",
            "典当行典当",
        )
        return (
            f"典当成功!\n"
            f"已抵押{item_name} x {quantity}\n"
            f"借得金币: {total_loan:,}\n"
            f"赎回需支付: {redeem_amount:,}金币"
            f"（含利息{redeem_amount - total_loan:,}）\n"
            f"赎回期限: {_get_redeem_days()}天"
        )

    async def redeem_item(self, ticket_id: int) -> str:
        """赎回典当道具，归还本金并支付利息

        参数:
            ticket_id: 当票ID

        返回:
            str: 操作结果消息
        """
        ticket = await PawnTicket.get_ticket(ticket_id)
        if not ticket:
            return "当票不存在"
        if ticket.user_id != self.user_id:
            return "这张当票不属于你"
        if ticket.status != _STATUS_ACTIVE:
            return "该当票已不在活跃状态，无法赎回"

        redeem_amount = int(
            ticket.loan_amount * (1 + ticket.interest_rate)
        )

        current_gold = await UserGold.get_user_gold(self.user_id)
        if current_gold < redeem_amount:
            return (
                f"金币不足! 赎回需要{redeem_amount:,}金币，"
                f"当前拥有{current_gold:,}金币"
            )

        success = await UserGold.reduce_user_gold(
            self.user_id, redeem_amount, source="典当行赎回"
        )
        if not success:
            return f"金币扣除失败，赎回需要{redeem_amount:,}金币"

        await self.inventory.add(ticket.item_id, ticket.quantity)

        ticket.status = _STATUS_REDEEMED
        ticket.redeemed_at = datetime.now()
        await ticket.save(update_fields=["status", "redeemed_at"])

        item_name = ticket.get_data().get("name", ticket.item_id)
        updated_gold = await UserGold.get_user_gold(self.user_id)
        logger.info(
            f"典当行赎回: 当票#{ticket_id}, {item_name} x {ticket.quantity}, "
            f"支付: {redeem_amount}, 用户: {self.user_id}",
            "典当行赎回",
        )
        return (
            f"赎回成功!\n"
            f"已赎回{item_name} x {ticket.quantity}\n"
            f"支付金币: {redeem_amount:,}"
            f"（本金{ticket.loan_amount:,}"
            f"+利息{redeem_amount - ticket.loan_amount:,}）\n"
            f"剩余金币: {updated_gold:,}"
        )

    async def get_my_tickets(self) -> list[dict]:
        """获取自己活跃的当票

        返回:
            list[dict]: 活跃当票字典列表
        """
        return await PawnTicket.get_user_tickets(
            self.user_id, status=_STATUS_ACTIVE
        )

    async def get_ticket_history(self) -> list[dict]:
        """获取自己的历史当票（已赎回/已没收）

        返回:
            list[dict]: 历史当票字典列表
        """
        tickets = await PawnTicket.filter(
            PawnTicket.user_id == self.user_id,
            PawnTicket.status.in_(_HISTORY_STATUSES),
        ).all()
        tickets = sorted(
            tickets, key=lambda t: t.pawn_at, reverse=True
        )
        return [t.to_dict() for t in tickets]

    @classmethod
    async def process_expired(cls) -> int:
        """处理逾期当票，将状态改为没收

        返回:
            int: 处理的逾期当票数量
        """
        expired = await PawnTicket.foreclose_expired()
        if not expired:
            return 0

        count = 0
        for ticket in expired:
            ticket.status = _STATUS_FORECLOSED
            await ticket.save(update_fields=["status"])
            count += 1

        logger.info(
            f"典当行逾期处理: 共没收{count}张逾期当票",
            "典当行逾期处理",
        )
        return count


__all__ = ["PawnshopService"]
