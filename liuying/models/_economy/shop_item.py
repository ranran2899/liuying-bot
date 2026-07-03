from datetime import datetime
from typing import ClassVar

import orjson as json
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class ShopItem(Model):
    """商店上架物品模型类"""

    __tablename__ = "shop_item"
    __table_args__: ClassVar[dict] = {"comment": "商店上架物品表"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    shop_name: Mapped[str] = mapped_column(String(255), index=True, comment="商店名称")
    quantity: Mapped[int] = mapped_column(default=1, comment="上架数量")
    price: Mapped[int] = mapped_column(default=0, comment="出售价格")
    seller_id: Mapped[str] = mapped_column(String(255), comment="卖家用户ID")
    item_data: Mapped[str] = mapped_column(Text, default="{}", comment="道具信息JSON")
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.now, comment="上架时间"
    )

    def get_data(self) -> dict:
        """获取道具数据字典"""
        try:
            return json.loads(self.item_data)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_data(self, data: dict):
        """设置道具数据"""
        self.item_data = json.dumps(data).decode()

    def to_dict(self) -> dict:
        """将上架物品转换为字典"""
        data = self.get_data()
        data["shop_name"] = self.shop_name
        data["quantity"] = self.quantity
        data["price"] = self.price
        data["seller_id"] = self.seller_id
        return data

    @classmethod
    async def _find_by_item_id(cls, shop_name: str, item_id: str) -> "ShopItem | None":
        """
        通过道具ID在JSON中查找上架物品

        参数:
            shop_name: 商店名称
            item_id: 道具ID

        返回:
            ShopItem | None: 上架物品实例
        """
        items = await cls.filter(shop_name=shop_name).all()
        for i in items:
            if i.get_data().get("id") == item_id:
                return i
        return None

    @classmethod
    async def add_item(
        cls,
        shop_name: str,
        item_id: str,
        quantity: int,
        price: int,
        seller_id: str,
        item_data: dict,
    ) -> bool:
        """
        添加上架物品，同一商店同一道具重复上架时累加数量并更新价格

        参数:
            shop_name: 商店名称
            item_id: 道具ID
            quantity: 上架数量
            price: 出售价格
            seller_id: 卖家用户ID
            item_data: 道具信息字典

        返回:
            bool: 是否添加成功
        """
        if quantity <= 0 or price < 0:
            return False

        existing = await cls._find_by_item_id(shop_name, item_id)
        if existing:
            existing.quantity += quantity
            existing.price = price
            await existing.save(update_fields=["quantity", "price"])
            return True

        store_data = {"id": item_id, **item_data}
        await cls.create(
            shop_name=shop_name,
            quantity=quantity,
            price=price,
            seller_id=seller_id,
            item_data=json.dumps(store_data).decode(),
        )
        return True

    @classmethod
    async def get_shop_items(cls, shop_name: str) -> list[dict]:
        """
        获取商店上架物品列表

        参数:
            shop_name: 商店名称

        返回:
            list[dict]: 上架物品字典列表
        """
        items = await cls.filter(shop_name=shop_name).all()
        return [item.to_dict() for item in items]

    @classmethod
    async def get_item(cls, shop_name: str, item_id: str) -> dict | None:
        """
        获取商店中的指定物品

        参数:
            shop_name: 商店名称
            item_id: 道具ID

        返回:
            dict | None: 物品信息字典
        """
        item = await cls._find_by_item_id(shop_name, item_id)
        return item.to_dict() if item else None

    @classmethod
    async def reduce_quantity(cls, shop_name: str, item_id: str, quantity: int) -> bool:
        """
        减少上架物品数量，数量归零时自动删除记录

        参数:
            shop_name: 商店名称
            item_id: 道具ID
            quantity: 减少数量

        返回:
            bool: 是否减少成功
        """
        item = await cls._find_by_item_id(shop_name, item_id)
        if not item or item.quantity < quantity:
            return False

        item.quantity -= quantity
        if item.quantity <= 0:
            await item.delete()
        else:
            await item.save(update_fields=["quantity"])
        return True

    @classmethod
    async def find_item_by_keyword(cls, shop_name: str, keyword: str) -> dict | None:
        """
        通过关键字查找商店物品（支持ID或名称）

        参数:
            shop_name: 商店名称
            keyword: 道具ID或名称

        返回:
            dict | None: 物品信息字典
        """
        items = await cls.filter(shop_name=shop_name).all()
        for i in items:
            data = i.get_data()
            if data.get("id") == keyword or data.get("name") == keyword:
                return i.to_dict()
        return None

    @classmethod
    async def update_price(cls, shop_name: str, item_id: str, new_price: int) -> bool:
        """修改商店物品价格

        参数:
            shop_name: 商店名称
            item_id: 道具ID
            new_price: 新价格

        返回:
            bool: 是否修改成功
        """
        if new_price < 0:
            return False
        item = await cls._find_by_item_id(shop_name, item_id)
        if not item:
            return False
        item.price = new_price
        await item.save(update_fields=["price"])
        return True

    @classmethod
    async def delist_item(cls, shop_name: str, item_id: str, quantity: int) -> int:
        """从商店下架物品，减少数量或删除记录

        参数:
            shop_name: 商店名称
            item_id: 道具ID
            quantity: 下架数量

        返回:
            int: 实际下架的数量，0表示失败
        """
        item = await cls._find_by_item_id(shop_name, item_id)
        if not item:
            return 0
        delisted = min(quantity, item.quantity)
        item.quantity -= delisted
        if item.quantity <= 0:
            await item.delete()
        else:
            await item.save(update_fields=["quantity"])
        return delisted

    @classmethod
    async def get_all_shop_items(cls) -> list[dict]:
        """获取所有商店的所有上架物品

        返回:
            list[dict]: 所有上架物品字典列表
        """
        items = await cls.filter().all()
        return [item.to_dict() for item in items]

    @classmethod
    def _run_script(cls):
        """数据库迁移脚本"""
        return [
            "CREATE TABLE IF NOT EXISTS shop_item ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "shop_name VARCHAR(255), "
            "quantity INTEGER DEFAULT 1, "
            "price INTEGER DEFAULT 0, "
            "seller_id VARCHAR(255), "
            "item_data TEXT DEFAULT '{}', "
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP);",
            "CREATE INDEX IF NOT EXISTS ix_shop_item_shop_name "
            "ON shop_item (shop_name);",
        ]
