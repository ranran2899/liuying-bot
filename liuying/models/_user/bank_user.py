"""银行用户模型"""

from datetime import datetime
from typing import ClassVar

from sqlalchemy import BigInteger, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class BankUser(Model):
    """银行用户模型类

    用于管理用户的银行账户信息，支持多币种存款
    """

    __tablename__ = "bank_user"
    __table_args__: ClassVar[dict] = {
        "comment": "银行用户表，用于管理用户银行账户信息"
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    """自增id"""
    user_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True, comment="用户id"
    )
    """用户id"""
    amount: Mapped[int] = mapped_column(
        BigInteger, default=0, comment="金币存款金额"
    )
    """金币存款金额"""
    rate: Mapped[float] = mapped_column(
        Float, default=0.0, comment="金币小时利率"
    )
    """金币小时利率"""
    silver_amount: Mapped[int] = mapped_column(
        BigInteger, default=0, comment="银币存款金额"
    )
    """银币存款金额"""
    copper_amount: Mapped[int] = mapped_column(
        BigInteger, default=0, comment="铜币存款金额"
    )
    """铜币存款金额"""
    loan_amount: Mapped[int] = mapped_column(
        BigInteger, default=0, comment="贷款金额"
    )
    """贷款金额"""
    loan_rate: Mapped[float] = mapped_column(
        Float, default=0.0, comment="贷款利率"
    )
    """贷款利率"""
    loan_due_date: Mapped[datetime | None] = mapped_column(
        default=None, comment="贷款到期时间"
    )
    """贷款到期时间"""
    fixed_deposits: Mapped[str] = mapped_column(
        Text, default="{}", comment="定期存款JSON"
    )
    """定期存款JSON"""
    create_time: Mapped[datetime] = mapped_column(
        default=datetime.now, comment="创建时间"
    )
    """创建时间"""
    update_time: Mapped[datetime] = mapped_column(
        default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )
    """更新时间"""

    @classmethod
    async def deposit(
        cls, user_id: str, amount: int, rate: float, currency: str = "gold"
    ) -> "BankUser":
        """存款操作

        参数:
            user_id: 用户id
            amount: 存款金额
            rate: 利率
            currency: 货币类型 (gold/silver/copper)

        返回:
            BankUser: 银行用户实例
        """
        user, _ = await cls.get_or_create(user_id=user_id)
        match currency:
            case "gold":
                user.amount += amount
                user.rate = rate
            case "silver":
                user.silver_amount += amount
            case "copper":
                user.copper_amount += amount
        user.update_time = datetime.now()
        await user.save()
        return user

    @classmethod
    async def withdraw(
        cls, user_id: str, amount: int, currency: str = "gold"
    ) -> "BankUser":
        """取款操作

        参数:
            user_id: 用户id
            amount: 取款金额
            currency: 货币类型 (gold/silver/copper)

        返回:
            BankUser: 银行用户实例
        """
        user, _ = await cls.get_or_create(user_id=user_id)
        match currency:
            case "gold":
                user.amount -= amount
            case "silver":
                user.silver_amount -= amount
            case "copper":
                user.copper_amount -= amount
        user.update_time = datetime.now()
        await user.save()
        return user

    @classmethod
    async def get_deposit_amount(
        cls, user_id: str, currency: str = "gold"
    ) -> int:
        """获取用户指定货币的存款金额

        参数:
            user_id: 用户id
            currency: 货币类型 (gold/silver/copper)

        返回:
            int: 存款金额
        """
        user, _ = await cls.get_or_create(user_id=user_id)
        match currency:
            case "gold":
                return user.amount
            case "silver":
                return user.silver_amount
            case "copper":
                return user.copper_amount
            case _:
                return 0

    @classmethod
    def _run_script(cls):
        """添加银币、铜币、贷款到期时间、定期存款字段"""
        return [
            "ALTER TABLE bank_user ADD silver_amount BIGINT DEFAULT 0;",
            "ALTER TABLE bank_user ADD copper_amount BIGINT DEFAULT 0;",
            "ALTER TABLE bank_user ADD loan_due_date DATETIME DEFAULT NULL;",
            "ALTER TABLE bank_user ADD fixed_deposits TEXT DEFAULT '{}';",
        ]
