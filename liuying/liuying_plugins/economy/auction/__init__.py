"""拍卖行插件 - 提供物品上架、购买、搜索和分页浏览功能

自动同步个人商店中已上架的全部物品至拍卖行展示，
支持模糊搜索和分页浏览，确保交易安全可靠。
"""

from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, Match, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import Command, PluginExtraData, RegisterConfig
from liuying.utils.apscheduler import task_manager
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

from .render import AuctionRenderer
from .service import AuctionService

__plugin_meta__ = PluginMetadata(
    name="拍卖行",
    description="拍卖行，支持物品上架、购买、搜索和分页浏览，自动同步个人商店物品",
    usage="""使用说明：
    拍卖行 - 查看拍卖行物品列表（第一页）
    拍卖行购买 [物品名称] [数量] - 从拍卖行购买物品
    拍卖行上架 [物品名称] [价格] [数量] - 上架物品至拍卖行
    拍卖行翻页 [页码] [物品名称(可选)] - 翻页浏览拍卖行
    拍卖行搜索 [物品名称] - 搜索拍卖行物品
    拍卖行下架 [物品名称] [数量] - 下架拍卖行物品
    拍卖行改价 [物品名称] [新价格] - 修改上架价格
    我的拍卖 - 查看自己的上架物品
    拍卖行记录 [页码] - 查看交易记录
    拍卖行比价 [物品名称] - 跨店比价
    """,
    extra=PluginExtraData(
        author="liuying",
        version="0.2",
        menu_type="娱乐",
        commands=[
            Command(command="拍卖行"),
            Command(command="拍卖行购买", params=["物品名称", "数量"]),
            Command(command="拍卖行上架", params=["物品名称", "价格", "数量"]),
            Command(command="拍卖行翻页", params=["页码", "物品名称(可选)"]),
            Command(command="拍卖行搜索", params=["物品名称"]),
            Command(command="拍卖行下架", params=["物品名称", "数量"]),
            Command(command="拍卖行改价", params=["物品名称", "新价格"]),
            Command(command="我的拍卖"),
            Command(command="拍卖行记录", params=["页码"]),
            Command(command="拍卖行比价", params=["物品名称"]),
        ],
        configs=[
            RegisterConfig(
                key="AUCTION_FEE_RATE",
                value=0.05,
                help="交易手续费率，默认0.05(5%)",
                default_value=0.05,
                type=float,
            ),
            RegisterConfig(
                key="AUCTION_EXPIRE_DAYS",
                value=7,
                help="拍卖到期天数，默认7天",
                default_value=7,
                type=int,
            ),
            RegisterConfig(
                key="AUCTION_MAX_EXPIRE_DAYS",
                value=30,
                help="最大到期天数，默认30天",
                default_value=30,
                type=int,
            ),
        ],
    ).to_dict(),
)

auction_cmd = on_alconna(Alconna("拍卖行"), priority=500, block=True)
buy_cmd = on_alconna(
    Alconna("拍卖行购买", Args["item_keyword", str], Args["quantity?", int, 1]),
    priority=500,
    block=True,
)
list_cmd = on_alconna(
    Alconna(
        "拍卖行上架",
        Args["item_keyword", str],
        Args["price", int],
        Args["quantity?", int, 1],
    ),
    priority=500,
    block=True,
)
page_cmd = on_alconna(
    Alconna("拍卖行翻页", Args["page", int], Args["item_name?", str]),
    priority=500,
    block=True,
)
search_cmd = on_alconna(
    Alconna("拍卖行搜索", Args["item_name", str]),
    priority=500,
    block=True,
)
delist_cmd = on_alconna(
    Alconna(
        "拍卖行下架",
        Args["item_keyword", str],
        Args["quantity?", int, 1],
    ),
    priority=500,
    block=True,
)
change_price_cmd = on_alconna(
    Alconna(
        "拍卖行改价",
        Args["item_keyword", str],
        Args["new_price", int],
    ),
    priority=500,
    block=True,
)
my_auctions_cmd = on_alconna(
    Alconna("我的拍卖"),
    priority=500,
    block=True,
)
transaction_history_cmd = on_alconna(
    Alconna("拍卖行记录", Args["page?", int, 1]),
    priority=500,
    block=True,
)
compare_price_cmd = on_alconna(
    Alconna("拍卖行比价", Args["item_keyword", str]),
    priority=500,
    block=True,
)


@auction_cmd.handle()
async def _(session: Uninfo):
    """查看拍卖行第一页"""
    user_id = session.user.id
    logger.info("查看拍卖行", "拍卖行", session=session)

    items, total_pages, page = await AuctionService.get_items_page(page=1)

    if not items:
        await MessageUtils.build_message("拍卖行暂无物品上架").finish()

    image = await AuctionRenderer.render_auction(user_id, items, page, total_pages)
    await MessageUtils.build_message(image).finish()


@buy_cmd.handle()
async def _(session: Uninfo, item_keyword: str, quantity: Match[int]):
    """从拍卖行购买物品"""
    user_id = session.user.id
    buy_qty = quantity.result

    logger.info(
        f"拍卖行购买: {item_keyword} x {buy_qty}", "拍卖行购买", session=session
    )

    result = await AuctionService.buy_item(user_id, item_keyword, buy_qty)

    msg = result.message if result.success else f"购买失败: {result.message}"
    await MessageUtils.build_message(msg).finish()


@list_cmd.handle()
async def _(session: Uninfo, item_keyword: str, price: int, quantity: Match[int]):
    """在拍卖行上架物品"""
    user_id = session.user.id
    list_qty = quantity.result

    logger.info(
        f"拍卖行上架: {item_keyword}, 价格: {price}, 数量: {list_qty}",
        "拍卖行上架",
        session=session,
    )

    result = await AuctionService.list_item(
        user_id, item_keyword, price, list_qty
    )

    if result.error:
        await MessageUtils.build_message(f"上架失败: {result.error}").finish()

    await MessageUtils.build_message(
        f"上架成功!\n已将{result.item_name} x {list_qty}"
        f"上架至拍卖行，价格为{price:,}金币/个"
    ).finish()


@page_cmd.handle()
async def _(session: Uninfo, page: int, item_name: Match[str]):
    """翻页浏览拍卖行"""
    user_id = session.user.id
    keyword = item_name.result.strip() if item_name.available else None

    logger.info(
        f"拍卖行翻页: 第{page}页" + (f", 搜索: {keyword}" if keyword else ""),
        "拍卖行翻页",
        session=session,
    )

    items, total_pages, current_page = await AuctionService.get_items_page(
        page=page, keyword=keyword
    )

    if not items:
        msg = (
            f"拍卖行中没有找到与'{keyword}'相关的物品"
            if keyword
            else "拍卖行暂无物品上架"
        )
        await MessageUtils.build_message(msg).finish()

    if current_page > total_pages:
        await MessageUtils.build_message(
            f"页码超出范围，当前共{total_pages}页"
        ).finish()

    image = await AuctionRenderer.render_auction(
        user_id, items, current_page, total_pages, keyword
    )
    await MessageUtils.build_message(image).finish()


@search_cmd.handle()
async def _(session: Uninfo, item_name: str):
    """搜索拍卖行物品"""
    user_id = session.user.id
    keyword = item_name.strip()

    logger.info(f"拍卖行搜索: {keyword}", "拍卖行搜索", session=session)

    results = await AuctionService.search_items(keyword)

    if not results:
        await MessageUtils.build_message(
            f"拍卖行中没有找到与'{keyword}'相关的物品"
        ).finish()

    total_pages = max(1, (len(results) + 19) // 20)
    image = await AuctionRenderer.render_auction(
        user_id, results, 1, total_pages, keyword
    )
    await MessageUtils.build_message(image).finish()


@delist_cmd.handle()
async def _(session: Uninfo, item_keyword: str, quantity: Match[int]):
    """下架拍卖行物品"""
    user_id = session.user.id
    delist_qty = quantity.result

    logger.info(
        f"拍卖行下架: {item_keyword} x {delist_qty}",
        "拍卖行下架",
        session=session,
    )

    result = await AuctionService.delist_item(
        user_id, item_keyword, delist_qty
    )

    msg = result.message if result.success else f"下架失败: {result.message}"
    await MessageUtils.build_message(msg).finish()


@change_price_cmd.handle()
async def _(session: Uninfo, item_keyword: str, new_price: int):
    """修改拍卖行上架价格"""
    user_id = session.user.id

    logger.info(
        f"拍卖行改价: {item_keyword} -> {new_price}",
        "拍卖行改价",
        session=session,
    )

    result = await AuctionService.change_price(
        user_id, item_keyword, new_price
    )

    msg = result.message if result.success else f"改价失败: {result.message}"
    await MessageUtils.build_message(msg).finish()


@my_auctions_cmd.handle()
async def _(session: Uninfo):
    """查看自己的上架物品"""
    user_id = session.user.id
    logger.info("我的拍卖", "我的拍卖", session=session)

    items = await AuctionService.get_my_auctions(user_id)

    if not items:
        await MessageUtils.build_message("你在拍卖行没有上架物品").finish()

    image = await AuctionRenderer.render_my_auctions(user_id, items)
    await MessageUtils.build_message(image).finish()


@transaction_history_cmd.handle()
async def _(session: Uninfo, page: Match[int]):
    """查看交易记录"""
    user_id = session.user.id
    page_num = page.result

    logger.info(
        f"拍卖行记录: 第{page_num}页", "拍卖行记录", session=session
    )

    records = await AuctionService.get_transaction_history(
        user_id, limit=20
    )

    if not records:
        await MessageUtils.build_message("暂无交易记录").finish()

    image = await AuctionRenderer.render_transaction_history(user_id, records)
    await MessageUtils.build_message(image).finish()


@compare_price_cmd.handle()
async def _(session: Uninfo, item_keyword: str):
    """跨店比价"""
    user_id = session.user.id
    keyword = item_keyword.strip()

    logger.info(
        f"拍卖行比价: {keyword}", "拍卖行比价", session=session
    )

    items = await AuctionService.compare_prices(keyword)

    if not items:
        await MessageUtils.build_message(
            f"没有找到与'{keyword}'相关的物品"
        ).finish()

    image = await AuctionRenderer.render_price_compare(user_id, items, keyword)
    await MessageUtils.build_message(image).finish()


@task_manager.cron_task(
    "auction_expire_check",
    hour=0,
    minute=5,
    name="拍卖行到期检查",
    group="auction",
)
async def _expire_auctions_task():
    """定时任务：每天检查到期拍卖并自动下架"""
    count = await AuctionService.expire_auctions()
    if count > 0:
        logger.info(
            f"拍卖行到期检查: 已自动下架{count}件到期物品",
            "拍卖行到期检查",
        )
