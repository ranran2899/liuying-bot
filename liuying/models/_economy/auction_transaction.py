"""拍卖行交易记录模型"""

from datetime import datetime
from typing import ClassVar

from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


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
