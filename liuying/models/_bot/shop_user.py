from datetime import datetime
from typing import ClassVar

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class ShopUser(Model):
    """用户商店模型类"""

    __tablename__ = "user_shop"
    __table_args__: ClassVar[dict] = {"comment": "用户商店表"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    shop_name: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, comment="商店名称"
    )
    owner_id: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, comment="店主用户ID"
    )
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.now, comment="创建时间"
    )

    @classmethod
    async def create_shop(cls, shop_name: str, owner_id: str) -> bool:
        """
        创建用户商店

        参数:
            shop_name: 商店名称
            owner_id: 店主用户ID

        返回:
            bool: 是否创建成功
        """
        if not shop_name or not owner_id:
            return False
        if await cls.filter(shop_name=shop_name).exists():
            return False
        if await cls.filter(owner_id=owner_id).exists():
            return False
        await cls.create(shop_name=shop_name, owner_id=owner_id)
        return True

    @classmethod
    async def get_shop_by_name(cls, shop_name: str) -> dict | None:
        """
        通过名称获取商店信息

        参数:
            shop_name: 商店名称

        返回:
            dict | None: 商店信息字典
        """
        if not shop_name:
            return None
        shop = await cls.filter(shop_name=shop_name).first()
        if not shop:
            return None
        return {
            "shop_name": shop.shop_name,
            "owner_id": shop.owner_id,
            "created_at": shop.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }

    @classmethod
    async def get_shop_by_owner(cls, owner_id: str) -> dict | None:
        """
        通过店主ID获取商店信息

        参数:
            owner_id: 店主用户ID

        返回:
            dict | None: 商店信息字典
        """
        if not owner_id:
            return None
        shop = await cls.filter(owner_id=owner_id).first()
        if not shop:
            return None
        return {
            "shop_name": shop.shop_name,
            "owner_id": shop.owner_id,
            "created_at": shop.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }

    @classmethod
    async def delete_shop(cls, shop_name: str) -> bool:
        """
        删除用户商店

        参数:
            shop_name: 商店名称

        返回:
            bool: 是否删除成功
        """
        shop = await cls.filter(shop_name=shop_name).first()
        if not shop:
            return False
        await shop.delete()
        return True

    @classmethod
    def _run_script(cls):
        """数据库迁移脚本"""
        return [
            "CREATE TABLE IF NOT EXISTS user_shop ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "shop_name VARCHAR(255) UNIQUE, "
            "owner_id VARCHAR(255) UNIQUE, "
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP);",
            "CREATE INDEX IF NOT EXISTS ix_user_shop_shop_name "
            "ON user_shop (shop_name);",
            "CREATE INDEX IF NOT EXISTS ix_user_shop_owner_id "
            "ON user_shop (owner_id);",
        ]
