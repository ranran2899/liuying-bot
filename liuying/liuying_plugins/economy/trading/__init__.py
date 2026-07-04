"""统一交易辅助模块

聚合拍卖行和商店的物品查询，解耦拍卖行服务对商店模型的直接依赖。
扁平化设计：VenueItem 数据类 + VenueAggregator 聚合器类，
无需抽象接口和适配器类。
"""

from dataclasses import dataclass


@dataclass(slots=True)
class VenueItem:
    """统一交易场所物品表示

    参数:
        id: 道具 ID
        name: 道具名称
        quantity: 上架数量
        price: 单价
        seller_id: 卖家用户 ID
        source: 来源类型，"auction" 或 "shop"
        venue_name: 场所名称（商店名或"拍卖行"）
        description: 道具描述
        type: 道具类型
        rarity: 道具稀有等级（1-5）
        image_url: 道具图片 URL
        expire_at: 到期时间字符串（拍卖行物品可能会有）
    """

    id: str
    name: str
    quantity: int
    price: int
    seller_id: str
    source: str
    venue_name: str = ""
    description: str = ""
    type: str = ""
    rarity: int = 1
    image_url: str = ""
    expire_at: str | None = None

    def to_dict(self) -> dict:
        """转换为字典，便于渲染层使用

        返回:
            dict: 渲染层兼容的字段字典
        """
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "type": self.type,
            "rarity": self.rarity,
            "image_url": self.image_url,
            "quantity": self.quantity,
            "price": self.price,
            "seller_id": self.seller_id,
            "source": self.source,
            "shop_name": self.venue_name,
            "item_id": self.id,
            "expire_at": self.expire_at,
        }


class VenueAggregator:
    """交易场所聚合器

    聚合拍卖行和个人商店的物品查询与库存扣减，
    对外提供统一的跨场所检索接口，屏蔽底层模型差异。
    所有方法均为静态方法，无实例状态。
    """

    @staticmethod
    def _match_keyword(item: VenueItem, keyword: str) -> bool:
        """检查物品是否匹配关键字（精确 ID/名称或模糊名称匹配）

        参数:
            item: 场所物品
            keyword: 搜索关键字

        返回:
            bool: 是否匹配
        """
        return (
            keyword == item.id
            or keyword == item.name
            or keyword in item.name
        )

    @staticmethod
    def _convert_auction(item: dict) -> VenueItem:
        """将拍卖行物品字典转换为 VenueItem

        参数:
            item: 拍卖行物品字典

        返回:
            VenueItem: 统一物品表示
        """
        return VenueItem(
            id=item.get("item_id", item.get("id", "")),
            name=item.get("name", ""),
            quantity=item.get("quantity", 0),
            price=item.get("price", 0),
            seller_id=item.get("seller_id", ""),
            source="auction",
            venue_name="拍卖行",
            description=item.get("description", ""),
            type=item.get("type", ""),
            rarity=item.get("rarity", 1),
            image_url=item.get("image_url", ""),
            expire_at=item.get("expire_at"),
        )

    @staticmethod
    def _convert_shop(item: dict) -> VenueItem:
        """将商店物品字典转换为 VenueItem

        参数:
            item: 商店物品字典

        返回:
            VenueItem: 统一物品表示
        """
        return VenueItem(
            id=item.get("id", ""),
            name=item.get("name", ""),
            quantity=item.get("quantity", 0),
            price=item.get("price", 0),
            seller_id=item.get("seller_id", ""),
            source="shop",
            venue_name=item.get("shop_name", ""),
            description=item.get("description", ""),
            type=item.get("type", ""),
            rarity=item.get("rarity", 1),
            image_url=item.get("image_url", ""),
        )

    @staticmethod
    async def get_all_venue_items() -> list[VenueItem]:
        """获取所有交易场所的上架物品（拍卖行 + 全部商店）

        返回:
            list[VenueItem]: 所有场所物品的聚合列表
        """
        from liuying.models._economy import AuctionItem, ShopItem
        from liuying.utils.log import logger

        all_items: list[VenueItem] = []

        try:
            auction_items = await AuctionItem.get_all_items()
            all_items.extend(
                VenueAggregator._convert_auction(item)
                for item in auction_items
            )
        except Exception as e:
            logger.error(f"获取拍卖行物品失败: {e}")

        try:
            shop_items = await ShopItem.get_all_shop_items()
            all_items.extend(
                VenueAggregator._convert_shop(item)
                for item in shop_items
            )
        except Exception as e:
            logger.error(f"获取商店物品失败: {e}")

        return all_items

    @staticmethod
    async def find_venue_items(keyword: str) -> list[VenueItem]:
        """在所有交易场所中查找匹配关键字的物品

        参数:
            keyword: 搜索关键字（道具 ID 或名称）

        返回:
            list[VenueItem]: 匹配的物品列表
        """
        all_items = await VenueAggregator.get_all_venue_items()
        return [
            item
            for item in all_items
            if VenueAggregator._match_keyword(item, keyword)
        ]

    @staticmethod
    async def reduce_venue_quantity(item: VenueItem, quantity: int) -> bool:
        """减少物品上架数量，归零时删除记录

        参数:
            item: 物品信息（需包含 source 和定位字段）
            quantity: 减少数量

        返回:
            bool: 是否减少成功
        """
        from liuying.models._economy import AuctionItem, ShopItem

        if item.source == "auction":
            return await AuctionItem.reduce_quantity(
                item.seller_id, item.id, quantity
            )
        if item.source == "shop":
            if not item.venue_name:
                return False
            return await ShopItem.reduce_quantity(
                item.venue_name, item.id, quantity
            )
        return False


__all__ = ["VenueAggregator", "VenueItem"]
