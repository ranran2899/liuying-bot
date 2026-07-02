"""银行日志模型"""

from datetime import datetime
from typing import ClassVar

from sqlalchemy import BigInteger, Boolean, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model
from liuying.utils.enum import BankHandleType


class BankLog(Model):
    """银行日志模型类

    用于记录用户的银行操作日志
    """

    __tablename__ = "bank_log"
    __table_args__: ClassVar[dict] = {
        "comment": "银行日志表，用于记录用户银行操作日志"
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    """自增id"""
    user_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="用户id"
    )
    """用户id"""
    amount: Mapped[int] = mapped_column(
        BigInteger, default=0, comment="金额"
    )
    """金额"""
    rate: Mapped[float] = mapped_column(
        Float, default=0.0, comment="利率"
    )
    """利率"""
    handle_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="操作类型"
    )
    """操作类型"""
    effective_hour: Mapped[int] = mapped_column(
        Integer, default=24, comment="有效小时数"
    )
    """有效小时数"""
    is_completed: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否已完成"
    )
    """是否已完成"""
    currency_type: Mapped[str] = mapped_column(
        String(50), default="gold", comment="货币类型 (gold/silver/copper)"
    )
    """货币类型 (gold/silver/copper)"""
    create_time: Mapped[datetime] = mapped_column(
        default=datetime.now, comment="创建时间"
    )
    """创建时间"""

    @classmethod
    async def get_user_today_deposit(
        cls, user_id: str, currency: str | None = None
    ) -> list["BankLog"]:
        """获取用户今日存款记录

        参数:
            user_id: 用户id
            currency: 货币类型，为None时返回所有货币类型

        返回:
            list[BankLog]: 存款记录列表
        """
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        filters = [
            cls.user_id == user_id,
            cls.handle_type == BankHandleType.DEPOSIT.value,
            cls.create_time >= today_start,
        ]
        if currency:
            filters.append(cls.currency_type == currency)
        return await cls.filter(*filters).all()

    @classmethod
    def _run_script(cls):
        """添加货币类型字段"""
        return [
            "ALTER TABLE bank_log ADD currency_type VARCHAR(50) DEFAULT 'gold';",
            "UPDATE bank_log SET currency_type = 'gold' WHERE currency_type IS NULL;",
        ]
