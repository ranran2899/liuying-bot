from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, Match, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import Command, PluginExtraData, RegisterConfig
from liuying.utils.log import logger

from .data import register_items as register_items
from .handlers import ShopHandler

__plugin_meta__ = PluginMetadata(
    name="商店",
    description="展示系统中已注册的道具信息，支持用户购买道具和创建个人商店",
    usage="""使用说明：
    商店 - 查看系统商店道具列表
    商店 [商店名称] - 查看指定用户商店
    购买道具 [道具名称/ID] [数量] - 购买指定道具
    使用道具 [道具名称/ID] [数量] - 使用指定道具
    我的道具 - 查看自己拥有的道具
    开店 [商店名称] - 创建个人商店
    商店上架 [道具名称/ID] [价格] [数量] - 上架道具至个人商店
    商店购买 [商店名称] [道具名称/ID] [数量] - 从用户商店购买道具
    商店下架 [道具名称/ID] [数量] - 从个人商店下架道具
    商店改价 [道具名称/ID] [新价格] - 修改个人商店物品价格
    我的商店 - 查看自己的商店信息和物品
    商店热销榜 - 查看热销道具排行榜
    商店记录 [页码] - 查看购买历史记录
    """,
    extra=PluginExtraData(
        author="liuying",
        version="0.7",
        commands=[
            Command(command="商店"),
            Command(command="购买道具"),
            Command(command="使用道具"),
            Command(command="我的道具"),
            Command(command="开店"),
            Command(command="商店上架"),
            Command(command="商店购买"),
            Command(command="商店下架"),
            Command(command="商店改价"),
            Command(command="我的商店"),
            Command(command="热销榜"),
            Command(command="商店记录"),
        ],
        configs=[
            RegisterConfig(
                key="STORE_SHOW_ITEMS",
                value=20,
                help="商店每次展示道具数量",
                default_value=20,
                type=int,
            ),
        ],
    ).to_dict(),
)

store_cmd = on_alconna(
    Alconna("商店", Args["shop_name?", str]),
    priority=500,
    block=True,
)
buy_cmd = on_alconna(
    Alconna("购买道具", Args["item_id", str], Args["quantity?", int]),
    priority=500,
    block=True,
)
use_cmd = on_alconna(
    Alconna("使用道具", Args["item_id", str], Args["quantity?", int]),
    priority=500,
    block=True,
)
my_items_cmd = on_alconna(
    Alconna("我的道具"),
    aliases={"/我的道具"},
    priority=500,
    block=True,
)
del_cmd = on_alconna(
    Alconna("删除道具", Args["item_id", str]),
    priority=500,
    block=True,
)
open_shop_cmd = on_alconna(
    Alconna("开店", Args["shop_name", str]),
    priority=500,
    block=True,
)
list_item_cmd = on_alconna(
    Alconna(
        "商店上架",
        Args["item_keyword", str],
        Args["price", int],
        Args["quantity?", int],
    ),
    priority=500,
    block=True,
)
buy_shop_cmd = on_alconna(
    Alconna(
        "商店购买",
        Args["shop_name", str],
        Args["item_keyword", str],
        Args["quantity?", int],
    ),
    priority=500,
    block=True,
)
delist_cmd = on_alconna(
    Alconna(
        "商店下架",
        Args["item_keyword", str],
        Args["quantity?", int],
    ),
    priority=500,
    block=True,
)
change_price_cmd = on_alconna(
    Alconna(
        "商店改价",
        Args["item_keyword", str],
        Args["new_price", int],
    ),
    priority=500,
    block=True,
)
my_shop_cmd = on_alconna(
    Alconna("我的商店"),
    priority=500,
    block=True,
)
hot_items_cmd = on_alconna(
    Alconna("商店热销榜"),
    priority=500,
    block=True,
)
shop_history_cmd = on_alconna(
    Alconna("商店记录", Args["page?", int, 1]),
    priority=500,
    block=True,
)


@store_cmd.handle()
async def _(session: Uninfo, shop_name: Match[str]):
    """查看商店道具列表"""
    logger.info("用户查看商店请求", command="商店", session=session)
    await ShopHandler.store(session, shop_name)


@buy_cmd.handle()
async def _(session: Uninfo, item_id: str, quantity: Match[int]):
    """购买道具"""
    logger.info("用户购买道具请求", command="购买道具", session=session)
    await ShopHandler.buy(session, item_id, quantity)


@use_cmd.handle()
async def _(session: Uninfo, item_id: str, quantity: Match[int]):
    """使用道具"""
    logger.info("用户使用道具请求", command="使用道具", session=session)
    await ShopHandler.use(session, item_id, quantity)


@my_items_cmd.handle()
async def _(session: Uninfo):
    """查看自己拥有的道具"""
    logger.info("用户查看道具道具请求", command="我的道具", session=session)
    await ShopHandler.my_items(session)


@del_cmd.handle()
async def _(session: Uninfo, item_id: str):
    """删除道具"""
    logger.info("删除道具请求", command="删除道具", session=session)
    await ShopHandler.delete(session, item_id)


@open_shop_cmd.handle()
async def _(session: Uninfo, shop_name: str):
    """开店"""
    logger.info("用户开店请求", command="开店", session=session)
    await ShopHandler.open_shop(session, shop_name)


@list_item_cmd.handle()
async def _(session: Uninfo, item_keyword: str, price: int, quantity: Match[int]):
    """商店上架道具"""
    logger.info("用户商店上架道具请求", command="商店上架", session=session)
    await ShopHandler.list_item(session, item_keyword, price, quantity)


@buy_shop_cmd.handle()
async def _(session: Uninfo, shop_name: str, item_keyword: str, quantity: Match[int]):
    """商店购买道具"""
    logger.info("用户商店购买道具请求", command="商店购买", session=session)
    await ShopHandler.buy_shop(session, shop_name, item_keyword, quantity)


@delist_cmd.handle()
async def _(session: Uninfo, item_keyword: str, quantity: Match[int]):
    """商店下架道具"""
    logger.info("用户商店下架道具请求", command="商店下架", session=session)
    await ShopHandler.delist(session, item_keyword, quantity)


@change_price_cmd.handle()
async def _(session: Uninfo, item_keyword: str, new_price: int):
    """商店改价"""
    logger.info("用户商店改价道具请求", command="商店改价", session=session)
    await ShopHandler.change_price(session, item_keyword, new_price)


@my_shop_cmd.handle()
async def _(session: Uninfo):
    """查看自己的商店"""
    logger.info("用户查看商店请求", command="我的商店", session=session)
    await ShopHandler.my_shop(session)


@hot_items_cmd.handle()
async def _(session: Uninfo):
    """查看热销道具"""
    logger.info("用户查看热销道具请求", command="商店热销榜", session=session)
    await ShopHandler.hot_items(session)


@shop_history_cmd.handle()
async def _(session: Uninfo, page: Match[int]):
    """查看商店记录"""
    logger.info("用户查看商店记录请求", command="商店记录", session=session)
    await ShopHandler.shop_history(session, page)

