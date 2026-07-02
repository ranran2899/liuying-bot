from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class Treasury(Model):
    """货币库模型类"""

    __tablename__ = "treasury"

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    name: Mapped[str] = mapped_column(
        String(255), default="default", comment="货币库名称"
    )
    money: Mapped[int] = mapped_column(
        BigInteger, default=0, comment="货币数量"
    )

    @classmethod
    async def get_treasury_money(cls, name: str) -> int:
        """获取货币库数量

        参数:
            name: 货币库名称

        返回:
            int: 货币库当前数量
        """
        treasury, _ = await cls.get_or_create(name=name)
        return treasury.money

    @classmethod
    async def update_treasury_money(cls, num: int, name: str) -> int:
        """修改货币库数量

        参数:
            num: 增减的数量
            name: 货币库名称

        返回:
            int: 货币库更新后的数量
        """
        treasury, created = await cls.get_or_create(
            name=name, defaults={"money": num}
        )
        if not created:
            treasury.money += num
            await treasury.save()
        return treasury.money

    @classmethod
    async def set_treasury_money(cls, amount: int, name: str) -> int:
        """设置货币库数量

        参数:
            amount: 设置的数量
            name: 货币库名称

        返回:
            int: 货币库当前数量
        """
        treasury, created = await cls.get_or_create(
            name=name, defaults={"money": amount}
        )
        if not created:
            treasury.money = amount
            await treasury.save()
        return treasury.money

    @classmethod
    async def increase_treasury_money(cls, amount: int, name: str) -> int:
        """增加货币库数量

        参数:
            amount: 增加的数量
            name: 货币库名称

        返回:
            int: 货币库更新后的数量
        """
        treasury, created = await cls.get_or_create(
            name=name, defaults={"money": amount}
        )
        if not created:
            treasury.money += amount
            await treasury.save()
        return treasury.money

    @classmethod
    async def decrease_treasury_money(cls, amount: int, name: str) -> int:
        """减少货币库数量

        参数:
            amount: 减少的数量
            name: 货币库名称

        返回:
            int: 货币库更新后的数量
        """
        treasury, created = await cls.get_or_create(name=name)
        if not created:
            if treasury.money >= amount:
                treasury.money -= amount
            else:
                treasury.money = 0
            await treasury.save()
        return treasury.money
