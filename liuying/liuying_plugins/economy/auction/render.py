"""拍卖行图片渲染模块

基于项目UI渲染系统，将拍卖行物品列表渲染为图片。
统一扁平列表展示，按价格降序排列，来源内联显示。
所有显示颜色通过稀有度模块动态获取，禁止硬编码颜色值。
"""

from datetime import datetime

from liuying.ui import render
from liuying.utils.user import UserMedia

from ..shop.rarity import RaritySystem

_TEMPLATE_PATH = "pages/builtin/auction"

_RENDER_FIELDS = (
    "id",
    "name",
    "description",
    "type",
    "rarity",
    "image_url",
)


class AuctionRenderer:
    """拍卖行渲染服务类

    封装拍卖行列表、我的上架、交易记录、比价结果的图片渲染逻辑，
    所有方法均为静态异步方法，统一使用项目UI渲染系统。
    """

    @staticmethod
    async def render_auction(
        user_id: str,
        items: list[dict],
        page: int,
        total_pages: int,
        keyword: str | None = None,
    ) -> bytes:
        """渲染拍卖行物品列表或搜索结果为图片

        参数:
            user_id: 用户ID
            items: 物品列表（已按价格降序排列）
            page: 当前页码
            total_pages: 总页数
            keyword: 搜索关键字

        返回:
            bytes: 图片字节数据
        """
        payload = await AuctionRenderer._build_payload(
            user_id, items, page, total_pages, keyword
        )
        return await render(
            _TEMPLATE_PATH,
            data={
                "page_type": "listing" if not keyword else "search",
                "payload": payload,
            },
            user_id=user_id,
            wait=2,
        )

    @staticmethod
    async def render_my_auctions(
        user_id: str, items: list[dict]
    ) -> bytes:
        """渲染我的拍卖页面

        参数:
            user_id: 用户ID
            items: 上架物品列表

        返回:
            bytes: 图片字节数据
        """
        user_ava = await UserMedia.get_avatar(user_id)
        item_list = [
            AuctionRenderer._extract(item, idx)
            for idx, item in enumerate(items)
        ]
        payload = {
            "item_list": item_list,
            "ava": user_ava,
            "total_count": len(item_list),
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        return await render(
            _TEMPLATE_PATH,
            data={"page_type": "my_auctions", "payload": payload},
            user_id=user_id,
            wait=2,
        )

    @staticmethod
    async def render_transaction_history(
        user_id: str, records: list[dict]
    ) -> bytes:
        """渲染交易记录

        参数:
            user_id: 用户ID
            records: 交易记录列表

        返回:
            bytes: 图片字节数据
        """
        user_ava = await UserMedia.get_avatar(user_id)
        record_list = [
            AuctionRenderer._build_record(r, idx)
            for idx, r in enumerate(records)
        ]
        payload = {
            "record_list": record_list,
            "ava": user_ava,
            "total_count": len(record_list),
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        return await render(
            _TEMPLATE_PATH,
            data={"page_type": "transaction_history", "payload": payload},
            user_id=user_id,
            wait=2,
        )

    @staticmethod
    async def render_price_compare(
        user_id: str, items: list[dict], keyword: str
    ) -> bytes:
        """渲染比价结果

        参数:
            user_id: 用户ID
            items: 按价格升序排列的物品列表
            keyword: 搜索关键字

        返回:
            bytes: 图片字节数据
        """
        user_ava = await UserMedia.get_avatar(user_id)
        item_list = [
            AuctionRenderer._extract(item, idx)
            for idx, item in enumerate(items)
        ]
        payload = {
            "item_list": item_list,
            "ava": user_ava,
            "total_count": len(item_list),
            "keyword": keyword,
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        return await render(
            _TEMPLATE_PATH,
            data={"page_type": "price_compare", "payload": payload},
            user_id=user_id,
            wait=2,
        )

    @staticmethod
    async def _build_payload(
        user_id: str,
        items: list[dict],
        page: int,
        total_pages: int,
        keyword: str | None = None,
    ) -> dict:
        """构建列表页渲染数据

        参数:
            user_id: 用户ID
            items: 物品列表
            page: 当前页码
            total_pages: 总页数
            keyword: 搜索关键字

        返回:
            dict: 渲染数据字典
        """
        user_ava = await UserMedia.get_avatar(user_id)
        item_list = [
            AuctionRenderer._extract(item, idx)
            for idx, item in enumerate(items)
        ]
        return {
            "item_list": item_list,
            "ava": user_ava,
            "total_count": len(item_list),
            "page": page,
            "total_pages": total_pages,
            "keyword": keyword,
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    @staticmethod
    def _extract(item: dict, index: int) -> dict:
        """提取物品渲染数据

        通过 apply_to_dict 注入稀有度颜色与分级描述，
        禁止硬编码颜色值。

        参数:
            item: 原始物品数据
            index: 物品序号

        返回:
            dict: 渲染用物品数据字典
        """
        source = item.get("source", "auction")
        base_data = {key: item.get(key, "") for key in _RENDER_FIELDS}
        base_data = RaritySystem.apply_to_dict(base_data)
        return {
            **base_data,
            "price": item.get("price", 0),
            "quantity": item.get("quantity", 0),
            "source": source,
            "source_label": "拍卖行" if source == "auction" else "商店",
            "shop_name": item.get("shop_name", ""),
            "number": index + 1,
        }

    @staticmethod
    def _build_record(record: dict, index: int) -> dict:
        """构建交易记录渲染数据

        参数:
            record: 原始交易记录
            index: 记录序号

        返回:
            dict: 渲染用记录字典
        """
        record_type = record.get("type", "")
        return {
            "id": record.get("id", ""),
            "item_name": record.get("item_name", ""),
            "quantity": record.get("quantity", 0),
            "unit_price": record.get("unit_price", 0),
            "total_price": record.get("total_price", 0),
            "fee": record.get("fee", 0),
            "type": record_type,
            "type_label": "购买" if record_type == "buy" else "出售",
            "counterpart": (
                record.get("seller_id", "")
                if record_type == "buy"
                else record.get("buyer_id", "")
            ),
            "created_at": record.get("created_at", ""),
            "number": index + 1,
        }
