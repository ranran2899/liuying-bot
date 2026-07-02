"""商店交易日志模型"""

from datetime import datetime
from typing import ClassVar

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class ShopTransactionLog(Model):
    """商店交易日志模型类

    用于记录商店中的购买/出售交易记录
    """

    __tablename__ = "shop_transaction_log"
    __table_args__: ClassVar[dict] = {"comment": "商店交易日志表，记录商店购买出售记录"}

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    user_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="用户id"
    )
    item_id: Mapped[str] = mapped_column(String(255), nullable=False, comment="道具id")
    item_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="道具名称"
    )
    quantity: Mapped[int] = mapped_column(BigInteger, default=1, comment="数量")
    price: Mapped[int] = mapped_column(BigInteger, default=0, comment="单价")
    total_price: Mapped[int] = mapped_column(BigInteger, default=0, comment="总价")
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="来源: shop/auction"
    )
    target_shop: Mapped[str] = mapped_column(
        String(255), default="", comment="目标商店名"
    )
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.now, comment="创建时间"
    )

    @classmethod
    async def record_transaction(
        cls,
        user_id: str,
        item_id: str,
        item_name: str,
        quantity: int,
        price: int,
        source: str,
        target_shop: str = "",
    ) -> bool:
        """记录交易日志

        参数:
            user_id: 用户id
            item_id: 道具id
            item_name: 道具名称
            quantity: 交易数量
            price: 单价
            source: 来源(shop/auction)
            target_shop: 目标商店名

        返回:
            bool: 是否记录成功
        """
        try:
            await cls.create(
                user_id=user_id,
                item_id=item_id,
                item_name=item_name,
                quantity=quantity,
                price=price,
                total_price=price * quantity,
                source=source,
                target_shop=target_shop,
            )
            return True
        except Exception:
            return False

    @classmethod
    async def get_user_history(
        cls, user_id: str, limit: int = 20
    ) -> list["ShopTransactionLog"]:
        """获取用户交易历史

        参数:
            user_id: 用户id
            limit: 返回记录数量上限

        返回:
            list[ShopTransactionLog]: 交易记录列表
        """
        return await cls.filter(user_id=user_id).order_by("-id").limit(limit).all()

    @classmethod
    def _run_script(cls):
        """数据库迁移脚本"""
        return [
            "CREATE TABLE IF NOT EXISTS shop_transaction_log ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "user_id VARCHAR(255) NOT NULL, "
            "item_id VARCHAR(255) NOT NULL, "
            "item_name VARCHAR(255) NOT NULL, "
            "quantity BIGINT DEFAULT 1, "
            "price BIGINT DEFAULT 0, "
            "total_price BIGINT DEFAULT 0, "
            "source VARCHAR(50) NOT NULL, "
            "target_shop VARCHAR(255) DEFAULT '', "
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP);",
            "CREATE INDEX IF NOT EXISTS "
            "ix_shop_transaction_log_user_id "
            "ON shop_transaction_log (user_id);",
        ]
