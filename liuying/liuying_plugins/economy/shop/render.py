"""商店图片渲染模块

负责将商店数据渲染为图片字节。
按渲染模式分发到不同模板，提取并分组道具数据。
所有显示颜色通过稀有度模块动态获取，禁止硬编码颜色值。
"""

from datetime import datetime

from liuying.ui import render
from liuying.utils.user import UserMedia
from liuying.utils.utils import format_image_url

from .rarity import RaritySystem

_TEMPLATE_PATH = "pages/builtin/shop"


class ShopRenderer:
    """商店渲染器

    所有方法均为静态异步方法，按渲染模式分发到对应模板。
    """

    @staticmethod
    async def render_store(user_id: str, items: list) -> bytes:
        """渲染系统商店页面图片

        参数:
            user_id: 用户 ID
            items: 道具列表

        返回:
            bytes: 图片字节数据
        """
        return await ShopRenderer._render(user_id, items, mode="store")

    @staticmethod
    async def render_items(user_id: str, items: list) -> bytes:
        """渲染我的道具页面图片

        参数:
            user_id: 用户 ID
            items: 道具列表

        返回:
            bytes: 图片字节数据
        """
        return await ShopRenderer._render(user_id, items, mode="my_items")

    @staticmethod
    async def render_user_shop(
        user_id: str, shop_name: str, shop_items: list, owner_id: str
    ) -> bytes:
        """渲染用户商店页面图片

        参数:
            user_id: 查看者用户 ID
            shop_name: 商店名称
            shop_items: 商店道具列表
            owner_id: 商店拥有者 ID

        返回:
            bytes: 图片字节数据
        """
        owner_ava = await UserMedia.get_avatar(owner_id)
        owner_name = await UserMedia.get_nickname(owner_id) or owner_id
        return await ShopRenderer._render(
            user_id,
            shop_items,
            mode="user_shop",
            shop_name=shop_name,
            owner_ava=owner_ava,
            owner_name=owner_name,
        )

    @staticmethod
    async def render_hot_items(user_id: str, items: list) -> bytes:
        """渲染热销榜页面图片

        参数:
            user_id: 用户 ID
            items: 热销道具列表

        返回:
            bytes: 图片字节数据
        """
        return await ShopRenderer._render(user_id, items, mode="hot_items")

    @staticmethod
    async def render_shop_history(user_id: str, records: list) -> bytes:
        """渲染购买历史页面图片

        参数:
            user_id: 用户 ID
            records: 交易记录列表

        返回:
            bytes: 图片字节数据
        """
        history_items = [
            {
                "item_name": r.item_name,
                "quantity": r.quantity,
                "price": r.price,
                "total_price": r.total_price,
                "source": r.source,
                "target_shop": r.target_shop,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for r in records
        ]
        return await ShopRenderer._render(
            user_id, history_items, mode="shop_history"
        )

    @staticmethod
    async def _render(user_id: str, items: list, mode: str, **extra) -> bytes:
        """统一渲染入口

        参数:
            user_id: 用户 ID
            items: 道具列表
            mode: 渲染模式 store/my_items/user_shop/hot_items/shop_history
            **extra: 传递给 payload 的额外数据

        返回:
            bytes: 图片字节数据
        """
        payload = await ShopRenderer._build_payload(
            user_id, items, mode, **extra
        )
        return await render(
            _TEMPLATE_PATH,
            data={"page_type": mode, "payload": payload},
            user_id=user_id,
            wait=2,
        )

    @staticmethod
    async def _build_payload(
        user_id: str, items: list, mode: str = "store", **extra
    ) -> dict:
        """构建渲染数据

        参数:
            user_id: 用户 ID
            items: 道具列表
            mode: 渲染模式
            **extra: 额外数据字段

        返回:
            dict: 渲染数据字典
        """
        user_ava = await UserMedia.get_avatar(user_id)
        items_by_type = ShopRenderer._group_items(items, mode)
        total_items = sum(len(g["items"]) for g in items_by_type)

        payload = {
            "plugin_list": items_by_type,
            "ava": user_ava,
            "plugin_count": len(items_by_type),
            "available_count": total_items,
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        payload.update(extra)
        return payload

    @staticmethod
    def _group_items(items: list, mode: str = "store") -> list[dict]:
        """按类型分组道具

        参数:
            items: 道具列表
            mode: 渲染模式

        返回:
            list[dict]: 分组后的道具列表
        """
        items_by_type: dict[str, list] = {}
        for index, item in enumerate(items):
            item_data = ShopRenderer._extract_item_data(item, mode, index)
            item_type = item_data.get("type") or "普通"
            items_by_type.setdefault(item_type, []).append(item_data)

        if not items_by_type:
            return [{"name": "道具", "items": []}]
        return [
            {"name": t, "items": group} for t, group in items_by_type.items()
        ]

    @staticmethod
    def _extract_item_data(item: dict, mode: str, index: int) -> dict:
        """提取道具渲染数据

        通过稀有度注入函数注入颜色与分级描述，禁止硬编码颜色值。

        参数:
            item: 原始道具数据
            mode: 渲染模式
            index: 道具序号

        返回:
            dict: 渲染用道具数据字典
        """
        data = {
            "id": item.get("id", ""),
            "name": item.get("name", ""),
            "description": item.get("description", ""),
            "type": item.get("type", "普通"),
            "rarity": item.get("rarity", 1),
            "image_url": format_image_url(item.get("image_url", "")),
        }
        data = RaritySystem.apply_to_dict(data)

        match mode:
            case "store":
                discount = item.get("discount", 100)
                original_price = item.get("price", 0)
                data["price"] = original_price
                data["discounted_price"] = int(original_price * discount / 100)
                data["discount"] = discount
                data["number"] = index + 1
            case "my_items":
                data["count"] = item.get("count", 0)
            case "user_shop":
                data["price"] = item.get("price", 0)
                data["count"] = item.get("quantity", item.get("count", 0))
                data["number"] = index + 1
            case "hot_items":
                data["total"] = item.get("total", 0)
                data["price"] = item.get("price", 0)
                data["number"] = index + 1
            case "shop_history":
                data["item_name"] = item.get("item_name", "")
                data["quantity"] = item.get("quantity", 0)
                data["price"] = item.get("price", 0)
                data["total_price"] = item.get("total_price", 0)
                data["source"] = item.get("source", "")
                data["target_shop"] = item.get("target_shop", "")
                data["created_at"] = item.get("created_at", "")
                data["number"] = index + 1

        return data


__all__ = ["ShopRenderer"]
