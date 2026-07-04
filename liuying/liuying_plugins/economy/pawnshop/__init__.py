"""典当行插件 - 提供道具典当、赎回和当票查询功能

抵押道具借出金币，到期赎回需还本付息，
逾期未赎回的当票将被没收处理。
"""

from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, Match, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import Command, PluginExtraData, RegisterConfig
from liuying.utils.apscheduler import task_manager
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

from .service import PawnshopService

__plugin_meta__ = PluginMetadata(
    name="典当行",
    description="典当行，抵押道具借金币，到期赎回还本付息",
    usage="""使用说明：
    典当 [物品名称] [数量] - 典当道具借出金币
    赎回 [当票ID] - 赎回典当的道具
    我的当票 - 查看活跃的当票
    典当记录 - 查看历史当票
    """,
    extra=PluginExtraData(
        author="liuying",
        version="0.1",
        menu_type="娱乐",
        commands=[
            Command(command="典当", params=["物品名称", "数量"]),
            Command(command="赎回", params=["当票ID"]),
            Command(command="我的当票"),
            Command(command="典当记录"),
        ],
        configs=[
            RegisterConfig(
                key="PAWN_REDEEM_DAYS",
                value=7,
                help="赎回期限天数，默认7天",
                default_value=7,
                type=int,
            ),
        ],
    ).to_dict(),
)

pawn_cmd = on_alconna(
    Alconna(
        "典当", Args["item_keyword", str], Args["quantity?", int, 1]
    ),
    priority=500,
    block=True,
)
redeem_cmd = on_alconna(
    Alconna("赎回", Args["ticket_id", int]),
    priority=500,
    block=True,
)
my_tickets_cmd = on_alconna(
    Alconna("我的当票"),
    priority=500,
    block=True,
)
ticket_history_cmd = on_alconna(
    Alconna("典当记录"),
    priority=500,
    block=True,
)

_STATUS_LABELS = {
    "active": "活跃",
    "redeemed": "已赎回",
    "foreclosed": "已没收",
}


class PawnshopRenderer:
    """当票文本渲染器

    将当票列表格式化为多行文本展示。
    """

    @staticmethod
    def format_ticket(ticket: dict, index: int) -> str:
        """格式化单张当票为文本

        参数:
            ticket: 当票字典
            index: 序号

        返回:
            str: 格式化的当票文本
        """
        name = ticket.get("name") or ticket.get("item_id", "未知道具")
        quantity = ticket.get("quantity", 0)
        loan_amount = ticket.get("loan_amount", 0)
        interest_rate = ticket.get("interest_rate", 0)
        redeem_amount = int(loan_amount * (1 + interest_rate))
        redeem_due = ticket.get("redeem_due", "未知")
        status = _STATUS_LABELS.get(ticket.get("status", ""), "未知")
        ticket_id = ticket.get("id", "?")
        lines = [
            f"{index}. 当票#{ticket_id} - {name} x {quantity}",
            f"   借款: {loan_amount:,}金币 | 赎回: {redeem_amount:,}金币"
            f"（利息{redeem_amount - loan_amount:,}）",
            f"   状态: {status} | 截止: {redeem_due}",
        ]
        redeemed_at = ticket.get("redeemed_at")
        if redeemed_at:
            lines.append(f"   完成时间: {redeemed_at}")
        return "\n".join(lines)

    @staticmethod
    def format_tickets(tickets: list[dict], title: str) -> str:
        """格式化当票列表为文本

        参数:
            tickets: 当票字典列表
            title: 标题

        返回:
            str: 格式化的当票列表文本
        """
        if not tickets:
            return f"{title}\n暂无记录"
        lines = [title, ""]
        for i, ticket in enumerate(tickets, 1):
            lines.append(PawnshopRenderer.format_ticket(ticket, i))
            lines.append("")
        return "\n".join(lines).strip()


@pawn_cmd.handle()
async def _(
    session: Uninfo, item_keyword: str, quantity: Match[int]
):
    """典当道具"""
    user_id = session.user.id
    pawn_qty = max(1, quantity.result) if quantity.available else 1

    logger.info(
        f"典当: {item_keyword} x {pawn_qty}", "典当行典当", session=session
    )

    service = PawnshopService(user_id)
    msg = await service.pawn_item(item_keyword, pawn_qty)
    await MessageUtils.build_message(msg).finish()


@redeem_cmd.handle()
async def _(session: Uninfo, ticket_id: int):
    """赎回道具"""
    user_id = session.user.id

    logger.info(
        f"赎回: 当票#{ticket_id}", "典当行赎回", session=session
    )

    service = PawnshopService(user_id)
    msg = await service.redeem_item(ticket_id)
    await MessageUtils.build_message(msg).finish()


@my_tickets_cmd.handle()
async def _(session: Uninfo):
    """查看活跃当票"""
    user_id = session.user.id
    logger.info("我的当票", "典当行当票", session=session)

    service = PawnshopService(user_id)
    tickets = await service.get_my_tickets()

    msg = PawnshopRenderer.format_tickets(tickets, "我的当票")
    await MessageUtils.build_message(msg).finish()


@ticket_history_cmd.handle()
async def _(session: Uninfo):
    """查看典当记录"""
    user_id = session.user.id
    logger.info("典当记录", "典当行记录", session=session)

    service = PawnshopService(user_id)
    tickets = await service.get_ticket_history()

    msg = PawnshopRenderer.format_tickets(tickets, "典当记录")
    await MessageUtils.build_message(msg).finish()


@task_manager.cron_task(
    "pawnshop_expire_check",
    hour=0,
    minute=15,
    name="典当行逾期处理",
    group="pawnshop",
)
async def _pawnshop_expire_task():
    """定时任务：每天0:15处理逾期当票"""
    count = await PawnshopService.process_expired()
    if count > 0:
        logger.info(
            f"典当行逾期处理: 已没收{count}张逾期当票",
            "典当行逾期处理",
        )
