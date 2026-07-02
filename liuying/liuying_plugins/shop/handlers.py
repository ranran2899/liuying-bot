from nonebot_plugin_alconna import Match
from nonebot_plugin_uninfo import Uninfo

from liuying.models._bot import ItemTemplate, Shop, ShopItem
from liuying.models._log.shop_log import ShopTransactionLog
from liuying.utils.enum import PropHandle
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils
from liuying.utils.user import UserGold

from .handler import HandlerRegistry, UseResult
from .inventory import ItemInventory, ItemResolver, is_valid_time
from .render import (
    render_hot_items,
    render_items,
    render_shop_history,
    render_store,
    render_user_shop,
)
from .shop_service import ShopService, calc_discount


class ShopHandler:
    """商店命令处理器"""

    @staticmethod
    def _get_quantity(match: Match[int], default: int = 1) -> int:
        """从 Match 中获取数量值

        参数:
            match: Alconna Match 对象
            default: 默认值

        返回:
            int: 数量值
        """
        return max(default, match.result if match.available else default)

    @staticmethod
    async def store(session: Uninfo, shop_name: Match[str]) -> None:
        """处理商店命令"""
        user_id = session.user.id

        if shop_name.available and shop_name.result.strip():
            target_shop = shop_name.result.strip()
            shop_info = await Shop.get_shop_by_name(target_shop)
            if not shop_info:
                await MessageUtils.build_message(
                    f"商店'{target_shop}'不存在"
                ).finish()

            shop_items = await ShopItem.get_shop_items(target_shop)
            if not shop_items:
                await MessageUtils.build_message(
                    f"商店【{target_shop}】暂无上架物品"
                ).finish()

            image_bytes = await render_user_shop(
                user_id, target_shop, shop_items, shop_info["owner_id"]
            )
            await MessageUtils.build_message(image_bytes).finish()
        else:
            logger.info("用户查看商店", command="商店", session=session)
            all_items = await ItemResolver().get_visible_templates()
            image_bytes = await render_store(user_id, all_items)
            await MessageUtils.build_message(image_bytes).finish()

    @staticmethod
    async def buy(session: Uninfo, item_id: str, quantity: Match[int]) -> None:
        """处理购买命令"""
        user_id = session.user.id
        buy_quantity = ShopHandler._get_quantity(quantity)

        resolver = ItemResolver()
        item_info = await resolver.resolve_store_item(item_id)
        if not item_info:
            await MessageUtils.build_message(
                f"商店里没有'{item_id}'这个道具"
            ).finish()

        if not is_valid_time(item_info.get("limited_time", -1)):
            await MessageUtils.build_message("该道具已过期，无法购买").finish()

        inventory = ItemInventory(user_id)
        limit = item_info.get("limit_purchase", -1)
        if not await inventory.check_limit(item_info["id"], limit):
            await MessageUtils.build_message("已达到限购数量，无法继续购买").finish()

        discount = item_info.get("discount", 100)
        discounted_price = calc_discount(item_info["price"], discount)
        total_price = discounted_price * buy_quantity

        current_gold = await UserGold.get_user_gold(user_id)
        if current_gold < total_price:
            await MessageUtils.build_message(
                f"金币不足! 需要{total_price}金币，当前有{current_gold}金币"
            ).finish()

        await UserGold.reduce_user_gold(user_id, total_price)
        await inventory.add(item_info["id"], buy_quantity)
        await ItemTemplate.record_purchase(item_info["id"], buy_quantity)
        await ShopService.record_purchase_history(
            user_id,
            item_info["id"],
            item_info["name"],
            buy_quantity,
            discounted_price,
            source="shop",
        )

        updated_gold = await UserGold.get_user_gold(user_id)
        price_info = f"原价{item_info['price']}金币"
        if discount != 100:
            price_info += f"，折扣价{discounted_price}金币"

        await MessageUtils.build_message(
            f"购买成功!\n获得{item_info['name']} x {buy_quantity}\n"
            f"{price_info}\n花费{total_price}金币\n剩余金币: {updated_gold}"
        ).finish()

    @staticmethod
    async def use(session: Uninfo, item_id: str, quantity: Match[int]) -> None:
        """处理使用道具命令"""
        user_id = session.user.id
        use_quantity = ShopHandler._get_quantity(quantity)

        result = await ShopHandler._use_item(user_id, item_id, use_quantity)
        if result.success:
            await MessageUtils.build_message(result.message).finish()
        else:
            await MessageUtils.build_message(f"使用失败: {result.message}").finish()

    @staticmethod
    async def my_items(session: Uninfo) -> None:
        """处理我的道具命令"""
        user_id = session.user.id
        user_items = await ItemInventory(user_id).get_items()
        image_bytes = await render_items(user_id, user_items)
        await MessageUtils.build_message(image_bytes).finish()

    @staticmethod
    async def delete(session: Uninfo, item_id: str) -> None:
        """处理删除道具命令"""
        item_template = await ItemResolver().find_template(item_id)
        if not item_template:
            await MessageUtils.build_message(
                f"未找到'{item_id}'的道具模板"
            ).finish()

        await ItemTemplate.delete_template(item_id=item_template["id"])
        await MessageUtils.build_message(
            f"删除成功!\n已删除道具模板: {item_template['name']}\n"
            f"注意: 所有用户拥有的该道具也已被删除"
        ).finish()

    @staticmethod
    async def open_shop(session: Uninfo, shop_name: str) -> None:
        """处理开店命令"""
        user_id = session.user.id
        shop_name = shop_name.strip()

        error = await ShopService(user_id).create_shop(shop_name)
        if error:
            await MessageUtils.build_message(error).finish()

        await MessageUtils.build_message(
            f"开店成功! 你的商店名称为: {shop_name}"
        ).finish()

    @staticmethod
    async def list_item(
        session: Uninfo, item_keyword: str, price: int, quantity: Match[int]
    ) -> None:
        """处理商店上架命令"""
        user_id = session.user.id
        list_quantity = ShopHandler._get_quantity(quantity)

        result = await ShopService(user_id).list_item_in_shop(
            item_keyword, price, list_quantity
        )
        if result.error:
            await MessageUtils.build_message(result.error).finish()

        await MessageUtils.build_message(
            f"上架成功!\n已将{result.item_name} x {list_quantity}上架至你的商店"
            f"，价格为{price:,}金币/个"
        ).finish()

    @staticmethod
    async def buy_shop(
        session: Uninfo, shop_name: str, item_keyword: str, quantity: Match[int]
    ) -> None:
        """处理商店购买命令"""
        user_id = session.user.id
        buy_quantity = ShopHandler._get_quantity(quantity)
        shop_name = shop_name.strip()

        shop_info = await Shop.get_shop_by_name(shop_name)
        if not shop_info:
            await MessageUtils.build_message(f"商店'{shop_name}'不存在").finish()

        if shop_info["owner_id"] == user_id:
            await MessageUtils.build_message("不能购买自己商店的物品").finish()

        shop_item = await ShopItem.find_item_by_keyword(shop_name, item_keyword)
        if not shop_item:
            await MessageUtils.build_message(
                f"商店'{shop_name}'中没有'{item_keyword}'"
            ).finish()

        if shop_item["quantity"] < buy_quantity:
            await MessageUtils.build_message(
                f"该物品数量不足，当前库存: {shop_item['quantity']}"
            ).finish()

        total_price = shop_item["price"] * buy_quantity
        current_gold = await UserGold.get_user_gold(user_id)
        if current_gold < total_price:
            await MessageUtils.build_message(
                f"金币不足! 需要{total_price:,}金币，"
                f"当前有{current_gold:,}金币"
            ).finish()

        await UserGold.reduce_user_gold(user_id, total_price)
        await UserGold.add_user_gold(
            shop_info["owner_id"], total_price, source="商店出售"
        )
        await ItemInventory(user_id).add(shop_item["id"], buy_quantity)
        await ShopItem.reduce_quantity(shop_name, shop_item["id"], buy_quantity)
        await ShopService.record_purchase_history(
            user_id,
            shop_item["id"],
            shop_item.get("name", shop_item["id"]),
            buy_quantity,
            shop_item["price"],
            source="shop",
        )

        updated_gold = await UserGold.get_user_gold(user_id)
        item_name = shop_item.get("name", shop_item["id"])

        await MessageUtils.build_message(
            f"购买成功!\n从【{shop_name}】购买了{item_name} x {buy_quantity}\n"
            f"花费{total_price:,}金币\n剩余金币: {updated_gold:,}"
        ).finish()

    @staticmethod
    async def delist(
        session: Uninfo, item_keyword: str, quantity: Match[int]
    ) -> None:
        """处理商店下架命令"""
        user_id = session.user.id
        delist_quantity = ShopHandler._get_quantity(quantity)

        result = await ShopService(user_id).delist_item(item_keyword, delist_quantity)
        if result.error:
            await MessageUtils.build_message(result.error).finish()

        await MessageUtils.build_message(
            f"下架成功!\n已将{result.item_name} x {delist_quantity}"
            f"从商店下架并归还背包"
        ).finish()

    @staticmethod
    async def change_price(
        session: Uninfo, item_keyword: str, new_price: int
    ) -> None:
        """处理商店改价命令"""
        user_id = session.user.id

        result = await ShopService(user_id).change_price(item_keyword, new_price)
        if result.error:
            await MessageUtils.build_message(result.error).finish()

        await MessageUtils.build_message(
            f"改价成功!\n已将{result.item_name}的价格修改为{new_price:,}金币"
        ).finish()

    @staticmethod
    async def my_shop(session: Uninfo) -> None:
        """处理我的商店命令"""
        user_id = session.user.id

        shop_info = await ShopService(user_id).get_my_shop()
        if not shop_info:
            await MessageUtils.build_message(
                "你还没有商店，请先使用'开店'命令创建商店"
            ).finish()

        shop_items = shop_info.get("items", [])
        if not shop_items:
            await MessageUtils.build_message(
                f"你的商店【{shop_info['shop_name']}】暂无上架物品"
            ).finish()

        image_bytes = await render_user_shop(
            user_id, shop_info["shop_name"], shop_items, user_id
        )
        await MessageUtils.build_message(image_bytes).finish()

    @staticmethod
    async def hot_items(session: Uninfo) -> None:
        """处理热销榜命令"""
        user_id = session.user.id

        hot_items = await ShopService.get_hot_items()
        if not hot_items:
            await MessageUtils.build_message("暂无热销数据").finish()

        image_bytes = await render_hot_items(user_id, hot_items)
        await MessageUtils.build_message(image_bytes).finish()

    @staticmethod
    async def shop_history(session: Uninfo, page: Match[int]) -> None:
        """处理商店记录命令"""
        user_id = session.user.id
        limit = 20

        records = await ShopTransactionLog.get_user_history(user_id, limit=limit + 1)
        if not records:
            await MessageUtils.build_message("暂无购买记录").finish()

        has_next = len(records) > limit
        display_records = records[:limit]
        image_bytes = await render_shop_history(user_id, display_records)

        current_page = max(1, page.result) if page.available else 1
        page_info = f"第{current_page}页"
        if has_next:
            page_info += f"，还有更多记录，使用'商店记录 {current_page + 1}'查看"

        await MessageUtils.build_message(image_bytes).finish()

    @staticmethod
    async def _use_item(
        user_id: str, keyword: str, quantity: int = 1
    ) -> UseResult:
        """使用道具

        参数:
            user_id: 用户 ID
            keyword: 道具 ID 或名称
            quantity: 使用数量

        返回:
            UseResult: 使用结果
        """
        item_info = await ItemResolver().resolve_store_item(keyword)
        if not item_info:
            return UseResult(
                success=False,
                result_type=PropHandle.ITEM_NOT_FOUND,
                message=f"未找到道具: {keyword}",
            )

        item_id = item_info["id"]
        item_name = item_info["name"]

        inventory = ItemInventory(user_id)
        if not await inventory.check_enough(item_id, quantity):
            current = await inventory.get_count(item_id)
            return UseResult(
                success=False,
                result_type=PropHandle.INSUFFICIENT_ITEMS,
                message=f"{item_name}数量不足\n当前拥有: {current}",
            )

        handler = HandlerRegistry.get(item_id) or HandlerRegistry.get(item_name)
        if not handler:
            return UseResult(
                success=False,
                result_type=PropHandle.HANDLER_NOT_REGISTERED,
                message=f"道具 {item_name} 暂未实现使用功能",
            )

        result = await handler.use(user_id, item_info, quantity)
        if result.success:
            await inventory.reduce(item_id, quantity)
        return result