"""商店图片渲染模块"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import ClassVar

from liuying.ui import render
from liuying.utils.log import logger
from liuying.utils.user import UserMedia
from liuying.utils.utils import format_image_url

_TEMPLATE_PATH = "pages/builtin/shop"


class ShopItemRenderer(ABC):
    """商店道具自定义渲染器抽象基类

    其他插件可以继承此类并注册到 ShopRendererRegistry，
    实现对特定类型或特定道具的个性化展示。
    渲染器通过 target_types 和 target_items 指定作用范围，
    优先匹配 target_items(道具ID), 其次匹配 target_types(道具类型)。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """渲染器唯一标识名称"""

    @property
    def target_types(self) -> list[str]:
        """目标道具类型列表，空列表表示不按类型匹配"""
        return []

    @property
    def target_items(self) -> list[str]:
        """目标道具 ID 列表，空列表表示不按 ID 匹配"""
        return []

    async def enhance_item(self, item: dict) -> dict:
        """增强道具数据

        参数:
            item: 原始道具数据字典

        返回:
            dict: 增强后的道具数据字典
        """
        return item

    def get_item_css_class(self, item: dict) -> str:
        """获取道具自定义 CSS 类名

        参数:
            item: 道具数据字典

        返回:
            str: CSS 类名字符串
        """
        return ""

    def get_item_extra_html(self, item: dict) -> str:
        """获取道具额外 HTML 内容片段

        参数:
            item: 道具数据字典

        返回:
            str: HTML 内容字符串
        """
        return ""

    def get_item_inline_style(self, item: dict) -> str:
        """获取道具自定义内联样式

        参数:
            item: 道具数据字典

        返回:
            str: 内联样式字符串
        """
        return ""

    def get_custom_css(self) -> str:
        """获取渲染器自定义 CSS 样式

        返回:
            str: CSS 样式字符串
        """
        return ""


class ShopRendererRegistry:
    """商店渲染器注册表

    管理所有已注册的道具自定义渲染器，
    支持按道具类型或 ID 匹配对应的渲染器。
    渲染器匹配优先级: 道具 ID > 道具类型。
    """

    _renderers: ClassVar[dict[str, ShopItemRenderer]] = {}

    @classmethod
    def register(cls, renderer: ShopItemRenderer) -> bool:
        """注册自定义渲染器

        参数:
            renderer: 渲染器实例

        返回:
            bool: 是否注册成功
        """
        if not isinstance(renderer, ShopItemRenderer):
            logger.warning(f"无效的渲染器类型: {type(renderer)}")
            return False

        name = renderer.name
        if name in cls._renderers:
            logger.warning(f"渲染器'{name}'已存在，将被覆盖")

        cls._renderers[name] = renderer
        logger.info(f"商店渲染器注册成功: {name}")
        return True

    @classmethod
    def unregister(cls, name: str) -> bool:
        """注销渲染器

        参数:
            name: 渲染器名称

        返回:
            bool: 是否注销成功
        """
        if name not in cls._renderers:
            return False
        del cls._renderers[name]
        return True

    @classmethod
    def find_renderer(cls, item: dict) -> ShopItemRenderer | None:
        """查找匹配道具的渲染器

        优先匹配道具 ID, 其次匹配道具类型。

        参数:
            item: 道具数据字典

        返回:
            ShopItemRenderer | None: 匹配的渲染器实例
        """
        item_id = item.get("id", "")
        item_type = item.get("type", "")

        for renderer in cls._renderers.values():
            if item_id and renderer.target_items and item_id in renderer.target_items:
                return renderer
            if (
                item_type
                and renderer.target_types
                and item_type in renderer.target_types
            ):
                return renderer
        return None

    @classmethod
    async def apply_renderers(cls, items: list[dict]) -> list[dict]:
        """对所有道具应用匹配的渲染器

        参数:
            items: 道具数据列表

        返回:
            list[dict]: 增强后的道具数据列表
        """
        if not cls._renderers or not items:
            return items

        enhanced: list[dict] = []
        for item in items:
            renderer = cls.find_renderer(item)
            if renderer:
                item = await renderer.enhance_item(item)
                item["_custom_class"] = renderer.get_item_css_class(item)
                item["_extra_html"] = renderer.get_item_extra_html(item)
                item["_inline_style"] = renderer.get_item_inline_style(item)
            enhanced.append(item)
        return enhanced

    @classmethod
    def collect_custom_css(cls) -> str:
        """收集所有渲染器的自定义 CSS 样式

        返回:
            str: 合并后的 CSS 字符串
        """
        if not cls._renderers:
            return ""
        css_parts = [
            css.strip()
            for renderer in cls._renderers.values()
            if (css := renderer.get_custom_css())
        ]
        return "\n".join(css_parts)


async def render_store(user_id: str, items: list) -> bytes:
    """渲染系统商店页面图片

    参数:
        user_id: 用户 ID
        items: 道具列表

    返回:
        bytes: 图片字节数据
    """
    return await _render_shop(user_id, items, mode="store")


async def render_items(user_id: str, items: list) -> bytes:
    """渲染我的道具页面图片

    参数:
        user_id: 用户 ID
        items: 道具列表

    返回:
        bytes: 图片字节数据
    """
    return await _render_shop(user_id, items, mode="my_items")


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
    return await _render_shop(
        user_id,
        shop_items,
        mode="user_shop",
        shop_name=shop_name,
        owner_ava=owner_ava,
        owner_name=owner_name,
    )


async def render_hot_items(user_id: str, items: list) -> bytes:
    """渲染热销榜页面图片

    参数:
        user_id: 用户 ID
        items: 热销道具列表

    返回:
        bytes: 图片字节数据
    """
    return await _render_shop(user_id, items, mode="hot_items")


async def render_shop_history(user_id: str, records: list) -> bytes:
    """渲染购买历史页面图片

    参数:
        user_id: 用户 ID
        records: 交易记录列表

    返回:
        bytes: 图片字节数据
    """
    history_items = []
    for r in records:
        history_items.append(
            {
                "item_name": r.item_name,
                "quantity": r.quantity,
                "price": r.price,
                "total_price": r.total_price,
                "source": r.source,
                "target_shop": r.target_shop,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return await _render_shop(user_id, history_items, mode="shop_history")


async def _render_shop(user_id: str, items: list, mode: str, **extra) -> bytes:
    """统一渲染入口

    参数:
        user_id: 用户 ID
        items: 道具列表
        mode: 渲染模式 store/my_items/user_shop
        **extra: 传递给 payload 的额外数据

    返回:
        bytes: 图片字节数据
    """
    payload = await _build_payload(user_id, items, mode, **extra)
    return await render(
        _TEMPLATE_PATH,
        data={"page_type": mode, "payload": payload},
        user_id=user_id,
        wait=2,
    )


async def _build_payload(
    user_id: str, items: list, mode: str = "store", **extra
) -> dict:
    """构建渲染数据

    参数:
        user_id: 用户 ID
        items: 道具列表
        mode: 渲染模式 store/my_items/user_shop
        **extra: 额外数据字段

    返回:
        dict: 渲染数据字典
    """
    user_ava = await UserMedia.get_avatar(user_id)
    items = await ShopRendererRegistry.apply_renderers(items)
    items_by_type = _group_items(items, mode)
    total_items = sum(len(g["items"]) for g in items_by_type)

    payload = {
        "plugin_list": items_by_type,
        "ava": user_ava,
        "plugin_count": len(items_by_type),
        "available_count": total_items,
        "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "custom_css": ShopRendererRegistry.collect_custom_css(),
    }
    payload.update(extra)
    return payload


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
        item_data = _extract_item_data(item, mode, index)
        item_type = item_data.get("type") or "普通"
        items_by_type.setdefault(item_type, []).append(item_data)

    if not items_by_type:
        return [{"name": "道具", "items": []}]

    return [{"name": t, "items": group} for t, group in items_by_type.items()]


def _extract_item_data(item: dict, mode: str, index: int) -> dict:
    """提取道具渲染数据

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
        "image_url": format_image_url(item.get("image_url", "")),
        "name_color": item.get("name_color", ""),
        "description_color": item.get("description_color", ""),
        "custom_class": item.get("_custom_class", ""),
        "extra_html": item.get("_extra_html", ""),
        "inline_style": item.get("_inline_style", ""),
    }

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
