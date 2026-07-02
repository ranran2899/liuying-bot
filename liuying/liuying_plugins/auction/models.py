"""拍卖行插件数据库模型"""

from datetime import datetime, timedelta
from typing import ClassVar

import orjson as json
from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model

_TO_DICT_FIELDS = (
    "id",
    "name",
    "description",
    "type",
    "image_url",
    "name_color",
    "description_color",
)


class AuctionItem(Model):
    """拍卖行上架物品模型"""

    __tablename__ = "auction_item"
    __table_args__: ClassVar[dict] = {"comment": "拍卖行上架物品表"}

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    seller_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="卖家用户ID"
    )
    item_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="道具ID"
    )
    item_data: Mapped[str] = mapped_column(Text, default="{}", comment="道具信息JSON")
    quantity: Mapped[int] = mapped_column(Integer, default=1, comment="上架数量")
    price: Mapped[int] = mapped_column(Integer, default=0, comment="单价")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="上架时间"
    )
    expire_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None, comment="到期时间"
    )

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

    def set_data(self, data: dict):
        """设置道具信息JSON

        参数:
            data: 道具信息字典
        """
        self.item_data = json.dumps(data).decode()

    def to_dict(self) -> dict:
        """转换为统一展示字典

        返回:
            dict: 包含道具信息和上架信息的字典
        """
        data = self.get_data()
        return {
            **{key: data.get(key, "") for key in _TO_DICT_FIELDS},
            "quantity": self.quantity,
            "price": self.price,
            "seller_id": self.seller_id,
            "item_id": self.item_id,
            "source": "auction",
            "source_id": self.id,
            "expire_at": str(self.expire_at) if self.expire_at else None,
        }

    @classmethod
    async def add_item(
        cls,
        seller_id: str,
        item_id: str,
        quantity: int,
        price: int,
        item_data: dict,
        expire_days: int = 7,
    ) -> bool:
        """添加拍卖行上架物品，同一卖家同一道具重复上架时累加数量并更新价格

        参数:
            seller_id: 卖家用户ID
            item_id: 道具ID
            quantity: 上架数量
            price: 单价
            item_data: 道具信息字典
            expire_days: 到期天数，默认7天

        返回:
            bool: 是否添加成功
        """
        if quantity <= 0 or price < 0:
            return False

        expire_at = datetime.now() + timedelta(days=expire_days)

        existing = await cls._find_by_seller_and_item(seller_id, item_id)
        if existing:
            existing.quantity += quantity
            existing.price = price
            existing.set_data(item_data)
            existing.expire_at = expire_at
            await existing.save(
                update_fields=["quantity", "price", "item_data", "expire_at"]
            )
            return True

        await cls.create(
            seller_id=seller_id,
            item_id=item_id,
            quantity=quantity,
            price=price,
            item_data=json.dumps({"id": item_id, **item_data}).decode(),
            expire_at=expire_at,
        )
        return True

    @classmethod
    async def _find_by_seller_and_item(
        cls, seller_id: str, item_id: str
    ) -> "AuctionItem | None":
        """通过卖家ID和道具ID查找上架记录

        先按seller_id在数据库层过滤，再在Python中匹配item_id

        参数:
            seller_id: 卖家用户ID
            item_id: 道具ID

        返回:
            AuctionItem | None: 上架物品实例
        """
        items = await cls.filter(seller_id=seller_id).all()
        return next((item for item in items if item.item_id == item_id), None)

    @classmethod
    async def get_user_items(cls, seller_id: str) -> list[dict]:
        """获取用户在拍卖行的上架物品列表

        参数:
            seller_id: 卖家用户ID

        返回:
            list[dict]: 上架物品字典列表
        """
        items = await cls.filter(seller_id=seller_id).all()
        return [item.to_dict() for item in items]

    @classmethod
    async def get_user_listed_types(cls, seller_id: str) -> int:
        """获取用户在拍卖行上架的物品种类数

        参数:
            seller_id: 卖家用户ID

        返回:
            int: 物品种类数
        """
        return await cls.filter(seller_id=seller_id).count()

    @classmethod
    async def reduce_quantity(cls, seller_id: str, item_id: str, quantity: int) -> bool:
        """减少拍卖行物品数量，数量归零时自动删除记录

        参数:
            seller_id: 卖家用户ID
            item_id: 道具ID
            quantity: 减少数量

        返回:
            bool: 是否减少成功
        """
        item = await cls._find_by_seller_and_item(seller_id, item_id)
        if not item or item.quantity < quantity:
            return False

        item.quantity -= quantity
        if item.quantity <= 0:
            await item.delete()
        else:
            await item.save(update_fields=["quantity"])
        return True

    @classmethod
    async def delist_item(
        cls, seller_id: str, item_id: str, quantity: int
    ) -> tuple[int, dict | None]:
        """下架物品，减少数量或删除，返回被下架的数量和物品信息

        参数:
            seller_id: 卖家用户ID
            item_id: 道具ID
            quantity: 下架数量

        返回:
            tuple[int, dict | None]: (实际下架数量, 物品信息字典)
        """
        item = await cls._find_by_seller_and_item(seller_id, item_id)
        if not item:
            return 0, None

        delist_qty = min(quantity, item.quantity)
        item_data = item.to_dict()

        item.quantity -= delist_qty
        if item.quantity <= 0:
            await item.delete()
        else:
            await item.save(update_fields=["quantity"])

        return delist_qty, item_data

    @classmethod
    async def change_price(
        cls, seller_id: str, item_id: str, new_price: int
    ) -> bool:
        """修改上架价格

        参数:
            seller_id: 卖家用户ID
            item_id: 道具ID
            new_price: 新单价

        返回:
            bool: 是否修改成功
        """
        if new_price < 0:
            return False

        item = await cls._find_by_seller_and_item(seller_id, item_id)
        if not item:
            return False

        item.price = new_price
        await item.save(update_fields=["price"])
        return True

    @classmethod
    async def expire_items(cls) -> list["AuctionItem"]:
        """查找所有已过期的物品并返回列表

        返回:
            list[AuctionItem]: 已过期的物品列表
        """
        now = datetime.now()
        all_items = await cls.filter().all()
        return [item for item in all_items if item.expire_at and item.expire_at <= now]

    @classmethod
    async def get_all_items(cls) -> list[dict]:
        """获取拍卖行所有上架物品（排除已过期）

        返回:
            list[dict]: 上架物品字典列表
        """
        now = datetime.now()
        items = await cls.filter().all()
        return [
            item.to_dict()
            for item in items
            if not item.expire_at or item.expire_at > now
        ]

    @classmethod
    async def find_by_keyword(cls, keyword: str) -> list[dict]:
        """通过关键字搜索拍卖行物品（支持ID或名称模糊匹配，排除已过期）

        参数:
            keyword: 搜索关键字

        返回:
            list[dict]: 匹配的物品字典列表
        """
        all_items = await cls.get_all_items()
        return [
            item
            for item in all_items
            if keyword in item.get("name", "")
            or keyword in item.get("id", "")
            or keyword == item.get("id", "")
            or keyword == item.get("name", "")
        ]

    @classmethod
    def _run_script(cls):
        """数据库迁移脚本"""
        return [
            "CREATE TABLE IF NOT EXISTS auction_item ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "seller_id VARCHAR(255), "
            "item_id VARCHAR(255), "
            "item_data TEXT DEFAULT '{}', "
            "quantity INTEGER DEFAULT 1, "
            "price INTEGER DEFAULT 0, "
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
            "expire_at DATETIME DEFAULT NULL);",
            "CREATE INDEX IF NOT EXISTS ix_auction_item_seller_id "
            "ON auction_item (seller_id);",
            "CREATE INDEX IF NOT EXISTS ix_auction_item_item_id "
            "ON auction_item (item_id);",
            "ALTER TABLE auction_item ADD COLUMN expire_at DATETIME "
            "DEFAULT NULL;",
        ]


class AuctionTransaction(Model):
    """拍卖行交易记录模型"""

    __tablename__ = "auction_transaction"
    __table_args__: ClassVar[dict] = {"comment": "拍卖行交易记录表"}

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    buyer_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="买家用户ID"
    )
    seller_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="卖家用户ID"
    )
    item_id: Mapped[str] = mapped_column(String(255), nullable=False, comment="道具ID")
    item_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="道具名称"
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1, comment="交易数量")
    unit_price: Mapped[int] = mapped_column(Integer, default=0, comment="单价")
    total_price: Mapped[int] = mapped_column(BigInteger, default=0, comment="总价")
    fee: Mapped[int] = mapped_column(Integer, default=0, comment="交易手续费")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="交易时间"
    )

    @classmethod
    async def record_transaction(
        cls,
        buyer_id: str,
        seller_id: str,
        item_id: str,
        item_name: str,
        quantity: int,
        unit_price: int,
        fee: int = 0,
    ) -> "AuctionTransaction":
        """记录交易

        参数:
            buyer_id: 买家用户ID
            seller_id: 卖家用户ID
            item_id: 道具ID
            item_name: 道具名称
            quantity: 交易数量
            unit_price: 单价
            fee: 交易手续费，默认0

        返回:
            AuctionTransaction: 交易记录实例
        """
        return await cls.create(
            buyer_id=buyer_id,
            seller_id=seller_id,
            item_id=item_id,
            item_name=item_name,
            quantity=quantity,
            unit_price=unit_price,
            total_price=unit_price * quantity,
            fee=fee,
        )

    @classmethod
    async def _get_history(
        cls, field: str, user_id: str, limit: int = 20
    ) -> list[dict]:
        """获取用户交易记录（购买/出售通用）

        参数:
            field: 筛选字段名（buyer_id或seller_id）
            user_id: 用户ID
            limit: 返回条数上限

        返回:
            list[dict]: 交易记录字典列表
        """
        records = await cls.filter(**{field: user_id}).all()
        records.sort(key=lambda r: r.created_at, reverse=True)
        return [
            {
                "id": t.id,
                "item_name": t.item_name,
                "quantity": t.quantity,
                "unit_price": t.unit_price,
                "total_price": t.total_price,
                "fee": t.fee,
                "buyer_id": t.buyer_id,
                "seller_id": t.seller_id,
                "created_at": str(t.created_at),
            }
            for t in records[:limit]
        ]

    @classmethod
    async def get_user_buy_history(cls, user_id: str, limit: int = 20) -> list[dict]:
        """获取用户购买记录

        参数:
            user_id: 用户ID
            limit: 返回条数上限

        返回:
            list[dict]: 交易记录字典列表
        """
        return await cls._get_history("buyer_id", user_id, limit)

    @classmethod
    async def get_user_sell_history(cls, user_id: str, limit: int = 20) -> list[dict]:
        """获取用户出售记录

        参数:
            user_id: 用户ID
            limit: 返回条数上限

        返回:
            list[dict]: 交易记录字典列表
        """
        return await cls._get_history("seller_id", user_id, limit)

    @classmethod
    def _run_script(cls):
        """数据库迁移脚本"""
        return [
            "CREATE TABLE IF NOT EXISTS auction_transaction ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "buyer_id VARCHAR(255), "
            "seller_id VARCHAR(255), "
            "item_id VARCHAR(255), "
            "item_name VARCHAR(255), "
            "quantity INTEGER DEFAULT 1, "
            "unit_price INTEGER DEFAULT 0, "
            "total_price BIGINT DEFAULT 0, "
            "fee INTEGER DEFAULT 0, "
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP);",
            "CREATE INDEX IF NOT EXISTS ix_auction_transaction_buyer_id "
            "ON auction_transaction (buyer_id);",
            "CREATE INDEX IF NOT EXISTS ix_auction_transaction_seller_id "
            "ON auction_transaction (seller_id);",
            "ALTER TABLE auction_transaction ADD COLUMN fee INTEGER "
            "DEFAULT 0;",
        ]
