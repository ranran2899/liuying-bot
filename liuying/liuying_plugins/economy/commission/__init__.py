"""委托求购板插件 - 发布求购单等待其他玩家出售

支持发布求购单、查看求购列表、向求购单出售道具、
取消求购单和查看自己的求购。求购单创建时预扣金币，
满足时金币转给出售者，取消或过期时退还冻结金币。
"""

from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, Match, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import Command, PluginExtraData, RegisterConfig
from liuying.utils.apscheduler import task_manager
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

from .service import CommissionService

__plugin_meta__ = PluginMetadata(
    name="委托求购板",
    description="委托求购板，发布求购单等待其他玩家出售",
    usage="""使用说明：
    求购 [物品名称] [单价] [数量] - 发布求购单
    求购列表 - 查看所有求购单
    求购出售 [物品名称] [数量] - 向求购单出售道具
    求购取消 [物品名称] [数量] - 取消求购单
    我的求购 - 查看自己的求购单
    """,
    extra=PluginExtraData(
        author="liuying",
        version="0.1",
        menu_type="娱乐",
        commands=[
            Command(
                command="求购", params=["物品名称", "单价", "数量"]
            ),
            Command(command="求购列表"),
            Command(
                command="求购出售", params=["物品名称", "数量"]
            ),
            Command(
                command="求购取消", params=["物品名称", "数量"]
            ),
            Command(command="我的求购"),
        ],
        configs=[
            RegisterConfig(
                key="COMMISSION_EXPIRE_DAYS",
                value=3,
                help="求购单到期天数，默认3天",
                default_value=3,
                type=int,
            ),
        ],
    ).to_dict(),
)

place_cmd = on_alconna(
    Alconna(
        "求购",
        Args["item_keyword", str],
        Args["unit_price", int],
        Args["quantity?", int, 1],
    ),
    priority=500,
    block=True,
)
list_cmd = on_alconna(
    Alconna("求购列表"),
    priority=500,
    block=True,
)
sell_cmd = on_alconna(
    Alconna(
        "求购出售",
        Args["item_keyword", str],
        Args["quantity?", int, 1],
    ),
    priority=500,
    block=True,
)
cancel_cmd = on_alconna(
    Alconna(
        "求购取消",
        Args["item_keyword", str],
        Args["quantity?", int, 1],
    ),
    priority=500,
    block=True,
)
my_orders_cmd = on_alconna(
    Alconna("我的求购"),
    priority=500,
    block=True,
)


class CommissionRenderer:
    """求购单文本渲染器

    将求购单列表格式化为多行文本展示。
    """

    @staticmethod
    def _format_order(order: dict, index: int) -> str:
        """格式化单条求购单

        参数:
            order: 求购单字典
            index: 序号

        返回:
            str: 格式化后的文本
        """
        name = order.get("name", "未知道具")
        qty = order.get("quantity", 0)
        fulfilled = order.get("fulfilled_quantity", 0)
        price = order.get("unit_price", 0)
        expire = order.get("expire_at", "无")
        return (
            f"{index}. {name} x{qty} (已满足{fulfilled})\n"
            f"   单价: {price:,}金币  到期: {expire}"
        )

    @staticmethod
    def format_my_orders(orders: list[dict]) -> str:
        """格式化我的求购单列表

        参数:
            orders: 求购单字典列表

        返回:
            str: 格式化后的文本
        """
        if not orders:
            return "你没有任何求购单"
        lines = ["=== 我的求购单 ==="]
        for i, order in enumerate(orders, 1):
            lines.append(CommissionRenderer._format_order(order, i))
        return "\n".join(lines)

    @staticmethod
    def format_all_orders(orders: list[dict]) -> str:
        """格式化所有求购单列表

        参数:
            orders: 求购单字典列表

        返回:
            str: 格式化后的文本
        """
        if not orders:
            return "求购板暂无求购单"
        lines = ["=== 求购列表 ==="]
        for i, order in enumerate(orders, 1):
            lines.append(CommissionRenderer._format_order(order, i))
        return "\n".join(lines)


@place_cmd.handle()
async def _(
    session: Uninfo,
    item_keyword: str,
    unit_price: int,
    quantity: Match[int],
):
    """发布求购单"""
    user_id = session.user.id
    place_qty = quantity.result

    logger.info(
        f"求购: {item_keyword}, 单价: {unit_price}, 数量: {place_qty}",
        "求购",
        session=session,
    )

    service = CommissionService(user_id)
    msg = await service.place_order(item_keyword, unit_price, place_qty)
    await MessageUtils.build_message(msg).finish()


@list_cmd.handle()
async def _(session: Uninfo):
    """查看所有求购单"""
    user_id = session.user.id
    logger.info("求购列表", "求购列表", session=session)

    service = CommissionService(user_id)
    orders = await service.get_all_orders()
    await MessageUtils.build_message(
        CommissionRenderer.format_all_orders(orders)
    ).finish()


@sell_cmd.handle()
async def _(session: Uninfo, item_keyword: str, quantity: Match[int]):
    """向求购单出售道具"""
    user_id = session.user.id
    sell_qty = quantity.result

    logger.info(
        f"求购出售: {item_keyword} x {sell_qty}",
        "求购出售",
        session=session,
    )

    service = CommissionService(user_id)
    msg = await service.fulfill_order(item_keyword, sell_qty)
    await MessageUtils.build_message(msg).finish()


@cancel_cmd.handle()
async def _(session: Uninfo, item_keyword: str, quantity: Match[int]):
    """取消求购单"""
    user_id = session.user.id
    cancel_qty = quantity.result

    logger.info(
        f"求购取消: {item_keyword} x {cancel_qty}",
        "求购取消",
        session=session,
    )

    service = CommissionService(user_id)
    msg = await service.cancel_order(item_keyword, cancel_qty)
    await MessageUtils.build_message(msg).finish()


@my_orders_cmd.handle()
async def _(session: Uninfo):
    """查看自己的求购单"""
    user_id = session.user.id
    logger.info("我的求购", "我的求购", session=session)

    service = CommissionService(user_id)
    orders = await service.get_my_orders()
    await MessageUtils.build_message(
        CommissionRenderer.format_my_orders(orders)
    ).finish()


@task_manager.cron_task(
    "commission_expire_check",
    hour=0,
    minute=10,
    name="求购单到期检查",
    group="commission",
)
async def _expire_orders_task():
    """定时任务：每天检查到期求购单并退还冻结金币"""
    count = await CommissionService.expire_orders()
    if count > 0:
        logger.info(
            f"求购单到期检查: 已处理{count}个过期求购单",
            "求购单到期检查",
        )
