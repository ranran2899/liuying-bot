"""黑市插件 - 系统商店，定时刷新随机道具，匿名交易

黑市商品由系统定时刷新，价格在原价基础上浮动，
采用随机化名进行匿名交易，所有收入进入国库。
"""

from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, Match, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import Command, PluginExtraData
from liuying.utils.apscheduler import task_manager
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

from .service import BlackMarketService

__plugin_meta__ = PluginMetadata(
    name="黑市",
    description="黑市系统商店，定时刷新随机道具，匿名交易",
    usage="""使用说明：
    黑市 - 查看黑市商品列表
    黑市购买 [物品名称] [数量] - 购买黑市商品
    黑市刷新 - 手动刷新黑市商品（管理员）
    """,
    extra=PluginExtraData(
        author="liuying",
        version="0.1",
        menu_type="娱乐",
        commands=[
            Command(command="黑市"),
            Command(command="黑市购买", params=["物品名称", "数量"]),
            Command(command="黑市刷新"),
        ],
    ).to_dict(),
)

blackmarket_cmd = on_alconna(Alconna("黑市"), priority=500, block=True)
buy_cmd = on_alconna(
    Alconna("黑市购买", Args["item_keyword", str], Args["quantity?", int, 1]),
    priority=500,
    block=True,
)
refresh_cmd = on_alconna(
    Alconna("黑市刷新"),
    permission=SUPERUSER,
    priority=500,
    block=True,
)


def _resolve_quantity(match: Match[int]) -> int:
    """从Match中解析数量，未提供时默认为1

    参数:
        match: Alconna Match对象

    返回:
        int: 有效数量（最小为1）
    """
    return max(1, match.result) if match.available else 1


def _format_items(items: list[dict]) -> str:
    """格式化黑市商品列表为多行文本

    参数:
        items: 黑市商品字典列表

    返回:
        str: 多行文本展示
    """
    if not items:
        return "黑市暂无商品上架"
    lines = ["===== 黑市商品列表 ====="]
    for idx, item in enumerate(items, start=1):
        name = item.get("name", "未知道具")
        quantity = item.get("quantity", 0)
        price = item.get("price", 0)
        seller = item.get("seller_name", "神秘商人")
        lines.append(
            f"{idx}. {name} x{quantity} - {price:,}金币 [{seller}]"
        )
    return "\n".join(lines)


@blackmarket_cmd.handle()
async def _(session: Uninfo):
    """查看黑市商品列表"""
    user_id = session.user.id
    logger.info("查看黑市", "黑市", session=session)

    service = BlackMarketService(user_id)
    items = await service.get_all_items()

    await MessageUtils.build_message(_format_items(items)).finish()


@buy_cmd.handle()
async def _(session: Uninfo, item_keyword: str, quantity: Match[int]):
    """购买黑市商品"""
    user_id = session.user.id
    buy_qty = _resolve_quantity(quantity)

    logger.info(
        f"黑市购买: {item_keyword} x {buy_qty}", "黑市购买", session=session
    )

    service = BlackMarketService(user_id)
    result = await service.buy_item(item_keyword, buy_qty)

    await MessageUtils.build_message(result).finish()


@refresh_cmd.handle()
async def _(session: Uninfo):
    """手动刷新黑市商品（管理员）"""
    logger.info("手动刷新黑市", "黑市刷新", session=session)

    result = await BlackMarketService.refresh()

    await MessageUtils.build_message(result).finish()


@task_manager.cron_task(
    "blackmarket_refresh",
    hour="6,18",
    minute=0,
    name="黑市自动刷新",
    group="blackmarket",
)
async def _blackmarket_refresh_task():
    """定时任务：每天6:00和18:00自动刷新黑市"""
    result = await BlackMarketService.refresh()
    logger.info(f"黑市自动刷新完成: {result}", "黑市自动刷新")
