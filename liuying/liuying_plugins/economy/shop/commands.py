"""商店命令处理器

接收 NoneBot 命令匹配结果，提取参数并调用业务服务，
构建回复消息。不包含业务校验逻辑，保持命令层轻量。
"""

from nonebot_plugin_alconna import Match
from nonebot_plugin_uninfo import Uninfo

from liuying.models._economy import Shop, ShopItem
from liuying.models._log.shop_log import ShopTransactionLog
from liuying.utils.enum import PropHandle
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils
from liuying.utils.user import UserGold

from .inventory import ItemInventory
from .registry import UseResult, get_handler
from .render import ShopRenderer
from .service import ShopService, calc_discount
from .template import TemplateRepository, is_valid_time

_HISTORY_PAGE_SIZE = 20


class ShopCommands:
    """商店命令处理器

    所有方法均为静态异步方法，接收 Uninfo 与 Match 参数，
    完成业务调用后通过 MessageUtils 发送回复并结束会话。
    """

    @staticmethod
    async def store(session: Uninfo, shop_name: Match[str]) -> None:
        """处理商店命令：查看系统商店或指定用户商店"""
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

            image_bytes = await ShopRenderer.render_user_shop(
                user_id, target_shop, shop_items, shop_info["owner_id"]
            )
            await MessageUtils.build_message(image_bytes).finish()
            return

        logger.info("用户查看商店", command="商店", session=session)
        all_items = await TemplateRepository.get_visible()
        image_bytes = await ShopRenderer.render_store(user_id, all_items)
        await MessageUtils.build_message(image_bytes).finish()

    @staticmethod
    async def buy(session: Uninfo, item_id: str, quantity: Match[int]) -> None:
        """处理购买命令：从系统商店购买道具"""
        user_id = session.user.id
        buy_quantity = quantity.result

        item_info = await TemplateRepository.resolve(item_id)
        if not item_info:
            await MessageUtils.build_message(
                f"商店里没有'{item_id}'这个道具"
            ).finish()

        if not is_valid_time(item_info.get("limited_time", -1)):
            await MessageUtils.build_message("该道具已过期，无法购买").finish()

        limit = item_info.get("limit_purchase", -1)
        if not await ItemInventory.check_limit(
            user_id, item_info["id"], limit
        ):
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
        await ItemInventory.add(user_id, item_info["id"], buy_quantity)
        await TemplateRepository.record_purchase(item_info["id"], buy_quantity)
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
        use_quantity = quantity.result

        result = await ShopCommands._use_item(user_id, item_id, use_quantity)
        if result.success:
            await MessageUtils.build_message(result.message).finish()
        else:
            await MessageUtils.build_message(f"使用失败: {result.message}").finish()

    @staticmethod
    async def my_items(session: Uninfo) -> None:
        """处理我的道具命令"""
        user_id = session.user.id
        user_items = await ItemInventory.get_items(user_id)
        image_bytes = await ShopRenderer.render_items(user_id, user_items)
        await MessageUtils.build_message(image_bytes).finish()

    @staticmethod
    async def delete(session: Uninfo, item_id: str) -> None:
        """处理删除道具命令"""
        item_template = await TemplateRepository.find(item_id)
        if not item_template:
            await MessageUtils.build_message(
                f"未找到'{item_id}'的道具模板"
            ).finish()

        await TemplateRepository.delete(item_id=item_template["id"])
        await MessageUtils.build_message(
            f"删除成功!\n已删除道具模板: {item_template['name']}\n"
            f"注意: 所有用户拥有的该道具也已被删除"
        ).finish()

    @staticmethod
    async def open_shop(session: Uninfo, shop_name: str) -> None:
        """处理开店命令"""
        user_id = session.user.id
        shop_name = shop_name.strip()

        error = await ShopService.create_shop(user_id, shop_name)
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
        list_quantity = quantity.result

        result = await ShopService.list_item_in_shop(
            user_id, item_keyword, price, list_quantity
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
        """处理商店购买命令：从用户商店购买道具"""
        user_id = session.user.id
        buy_quantity = quantity.result
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
        await ItemInventory.add(user_id, shop_item["id"], buy_quantity)
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
        delist_quantity = quantity.result

        result = await ShopService.delist_item(
            user_id, item_keyword, delist_quantity
        )
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

        result = await ShopService.change_price(
            user_id, item_keyword, new_price
        )
        if result.error:
            await MessageUtils.build_message(result.error).finish()

        await MessageUtils.build_message(
            f"改价成功!\n已将{result.item_name}的价格修改为{new_price:,}金币"
        ).finish()

    @staticmethod
    async def my_shop(session: Uninfo) -> None:
        """处理我的商店命令"""
        user_id = session.user.id

        shop_info = await ShopService.get_my_shop(user_id)
        if not shop_info:
            await MessageUtils.build_message(
                "你还没有商店，请先使用'开店'命令创建商店"
            ).finish()

        shop_items = shop_info.get("items", [])
        if not shop_items:
            await MessageUtils.build_message(
                f"你的商店【{shop_info['shop_name']}】暂无上架物品"
            ).finish()

        image_bytes = await ShopRenderer.render_user_shop(
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

        image_bytes = await ShopRenderer.render_hot_items(user_id, hot_items)
        await MessageUtils.build_message(image_bytes).finish()

    @staticmethod
    async def shop_history(session: Uninfo, page: Match[int]) -> None:
        """处理商店记录命令"""
        user_id = session.user.id
        current_page = page.result
        offset = (current_page - 1) * _HISTORY_PAGE_SIZE

        records = await ShopTransactionLog.get_user_history(
            user_id, limit=_HISTORY_PAGE_SIZE + 1, offset=offset
        )
        if not records:
            await MessageUtils.build_message("暂无购买记录").finish()

        has_next = len(records) > _HISTORY_PAGE_SIZE
        display_records = records[:_HISTORY_PAGE_SIZE]
        image_bytes = await ShopRenderer.render_shop_history(
            user_id, display_records
        )

        page_info = f"第{current_page}页"
        if has_next:
            page_info += (
                f"，还有更多记录，使用'商店记录 {current_page + 1}'查看"
            )

        await MessageUtils.build_message([image_bytes, f"\n{page_info}"]).finish()

    @staticmethod
    async def _use_item(
        user_id: str, keyword: str, quantity: int = 1
    ) -> UseResult:
        """使用道具内部实现

        参数:
            user_id: 用户 ID
            keyword: 道具 ID 或名称
            quantity: 使用数量

        返回:
            UseResult: 使用结果
        """
        item_info = await TemplateRepository.resolve(keyword)
        if not item_info:
            return UseResult(
                success=False,
                result_type=PropHandle.ITEM_NOT_FOUND,
                message=f"未找到道具: {keyword}",
            )

        item_id = item_info["id"]
        item_name = item_info["name"]

        if not await ItemInventory.check_enough(user_id, item_id, quantity):
            current = await ItemInventory.get_count(user_id, item_id)
            return UseResult(
                success=False,
                result_type=PropHandle.INSUFFICIENT_ITEMS,
                message=f"{item_name}数量不足\n当前拥有: {current}",
            )

        entry = get_handler(item_id) or get_handler(item_name)
        if entry is None:
            return UseResult(
                success=False,
                result_type=PropHandle.HANDLER_NOT_REGISTERED,
                message=f"道具 {item_name} 暂未实现使用功能",
            )

        use_func, can_use_func, _ = entry
        if can_use_func is not None:
            if not await can_use_func(user_id, item_info):
                return UseResult(
                    success=False,
                    result_type=PropHandle.FAILED,
                    message=f"道具 {item_name} 当前无法使用",
                )

        result = await use_func(user_id, item_info, quantity)
        if result.success:
            await ItemInventory.reduce(user_id, item_id, quantity)
        return result


__all__ = ["ShopCommands"]
