"""黑市系统商店商品模型"""

from datetime import datetime
from typing import ClassVar

import orjson as json
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model

_TO_DICT_FIELDS = (
    "id",
    "name",
    "description",
    "type",
    "rarity",
    "image_url",
)


class BlackMarketItem(Model):
    """黑市系统商店商品模型"""

    __tablename__ = "blackmarket_item"
    __table_args__: ClassVar[dict] = {"comment": "黑市系统商店商品表"}

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    item_data: Mapped[str] = mapped_column(
        Text, default="{}", comment="道具信息JSON（含id字段）"
    )
    quantity: Mapped[int] = mapped_column(
        Integer, default=1, comment="库存数量"
    )
    price: Mapped[int] = mapped_column(
        Integer, default=0, comment="系统定价"
    )
    base_price: Mapped[int] = mapped_column(
        Integer, default=0, comment="基础价格"
    )
    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="刷新时间"
    )
    seller_name: Mapped[str] = mapped_column(
        String(255), default="神秘商人", comment="卖家化名"
    )

    @property
    def item_id(self) -> str:
        """道具ID（从item_data JSON的id字段读取）"""
        return self.get_data().get("id", "")

    def get_data(self) -> dict:
        """解析道具信息JSON

        返回:
            dict: 道具信息字典
        """
        try:
            data = json.loads(self.item_data)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_data(self, data: dict) -> None:
        """设置道具信息JSON

        参数:
            data: 道具信息字典
        """
        self.item_data = json.dumps(data).decode()

    def to_dict(self) -> dict:
        """转换为统一展示字典

        返回:
            dict: 包含道具信息和黑市信息的字典
        """
        data = self.get_data()
        return {
            **{key: data.get(key, "") for key in _TO_DICT_FIELDS},
            "quantity": self.quantity,
            "price": self.price,
            "base_price": self.base_price,
            "refreshed_at": (
                str(self.refreshed_at) if self.refreshed_at else None
            ),
            "seller_name": self.seller_name,
            "item_id": data.get("id", ""),
            "source": "blackmarket",
            "source_id": self.id,
        }

    @classmethod
    async def get_all_items(cls) -> list[dict]:
        """获取所有黑市商品

        返回:
            list[dict]: 黑市商品字典列表
        """
        items = await cls.filter().all()
        return [item.to_dict() for item in items]

    @classmethod
    async def find_by_keyword(cls, keyword: str) -> list[dict]:
        """通过关键字搜索黑市商品（支持ID或名称模糊匹配）

        参数:
            keyword: 搜索关键字

        返回:
            list[dict]: 匹配的商品字典列表
        """
        all_items = await cls.get_all_items()
        return [
            item
            for item in all_items
            if keyword in item.get("name", "")
            or keyword in item.get("item_id", "")
            or keyword == item.get("item_id", "")
            or keyword == item.get("name", "")
        ]

    @classmethod
    async def reduce_quantity(
        cls, item_id: str, quantity: int
    ) -> bool:
        """减少黑市商品库存，数量归零时自动删除记录

        参数:
            item_id: 道具ID
            quantity: 减少数量

        返回:
            bool: 是否减少成功
        """
        items = await cls.filter().all()
        target = next((it for it in items if it.item_id == item_id), None)
        if not target or target.quantity < quantity:
            return False
        target.quantity -= quantity
        if target.quantity <= 0:
            await target.delete()
        else:
            await target.save(update_fields=["quantity"])
        return True

    @classmethod
    async def clear_all(cls) -> int:
        """清空所有黑市商品

        返回:
            int: 清除的商品数量
        """
        items = await cls.filter().all()
        count = len(items)
        for item in items:
            await item.delete()
        return count

    @classmethod
    async def add_item(
        cls,
        item_id: str,
        item_data: dict,
        quantity: int,
        price: int,
        seller_name: str = "神秘商人",
    ) -> "BlackMarketItem":
        """添加黑市商品

        参数:
            item_id: 道具ID
            item_data: 道具信息字典，可包含price字段作为基础价格
            quantity: 库存数量
            price: 系统定价
            seller_name: 卖家化名，默认为"神秘商人"

        返回:
            BlackMarketItem: 创建的商品实例
        """
        base_price = int(item_data.get("price", price))
        return await cls.create(
            item_data=json.dumps({"id": item_id, **item_data}).decode(),
            quantity=quantity,
            price=price,
            base_price=base_price,
            seller_name=seller_name,
        )

    @classmethod
    def _run_script(cls) -> list[str]:
        """数据库迁移脚本"""
        return [
            "CREATE TABLE IF NOT EXISTS blackmarket_item ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "item_data TEXT DEFAULT '{}', "
            "quantity INTEGER DEFAULT 1, "
            "price INTEGER DEFAULT 0, "
            "base_price INTEGER DEFAULT 0, "
            "refreshed_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
            "seller_name VARCHAR(255) DEFAULT '神秘商人');",
            "ALTER TABLE blackmarket_item ADD COLUMN base_price "
            "INTEGER DEFAULT 0;",
            "ALTER TABLE blackmarket_item ADD COLUMN seller_name "
            "VARCHAR(255) DEFAULT '神秘商人';",
        ]
