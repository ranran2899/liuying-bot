"""用户货币日志模型类"""

from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model
from liuying.utils.enum import CurrHandle


class UserCurrLog(Model):
    """用户货币日志模型类
    
    用于记录用户货币变动记录
    """

    __tablename__ = "user_curr_log"
    __table_args__ = {"comment": "用户货币记录表，用于记录用户货币变动"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="自增id")
    """自增id"""
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True, comment="用户id")
    """用户id"""
    copper: Mapped[int] = mapped_column(default=0, comment="铜币")
    """铜币"""
    silver: Mapped[int] = mapped_column(default=0, comment="银币")
    """银币"""
    gold: Mapped[int] = mapped_column(default=0, comment="金币")
    """金币"""
    diamond: Mapped[int] = mapped_column(default=0, comment="钻石")
    """钻石"""
    xingqiong: Mapped[int] = mapped_column(default=0, comment="星琼")
    """星琼数"""
    yuanshi: Mapped[int] = mapped_column(default=0, comment="原石")
    """原石"""
    tianrew: Mapped[int] = mapped_column(default=0, comment="天赏点")
    """天赏点"""
    handle: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="货币处理类型")
    """货币处理类型"""
    source: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="来源插件")
    """来源插件"""
    create_time: Mapped[datetime] = mapped_column(default=datetime.now, comment="创建时间")
    """创建时间"""

    @classmethod
    async def create_gold_log(
        cls,
        user_id: str,
        gold: int,
        handle: CurrHandle | str,
        source: str | None = None
    ) -> "UserCurrLog":
        """创建金币变动日志

        参数:
            user_id: 用户ID
            gold: 金币数量
            handle: 金币处理类型
            source: 来源

        返回:
            UserCurrLog: 创建的日志记录
        """
        handle_value = handle.value if isinstance(handle, CurrHandle) else handle
        return await cls.create(
            user_id=user_id,
            gold=gold,
            handle=handle_value,
            source=source,
            db_name="log_db"
        )

    @classmethod
    async def create_copper_log(
        cls,
        user_id: str,
        copper: int,
        handle: CurrHandle | str,
        source: str | None = None
    ) -> "UserCurrLog":
        """创建铜币变动日志

        参数:
            user_id: 用户ID
            copper: 铜币数量
            handle: 货币处理类型
            source: 来源

        返回:
            UserCurrLog: 创建的日志记录
        """
        handle_value = handle.value if isinstance(handle, CurrHandle) else handle
        return await cls.create(
            user_id=user_id,
            copper=copper,
            handle=handle_value,
            source=source,
            db_name="log_db"
        )

    @classmethod
    async def create_silver_log(
        cls,
        user_id: str,
        silver: int,
        handle: CurrHandle | str,
        source: str | None = None
    ) -> "UserCurrLog":
        """创建银币变动日志

        参数:
            user_id: 用户ID
            silver: 银币数量
            handle: 货币处理类型
            source: 来源

        返回:
            UserCurrLog: 创建的日志记录
        """
        handle_value = handle.value if isinstance(handle, CurrHandle) else handle
        return await cls.create(
            user_id=user_id,
            silver=silver,
            handle=handle_value,
            source=source,
            db_name="log_db"
        )

    @classmethod
    async def create_diamond_log(
        cls,
        user_id: str,
        diamond: int,
        handle: CurrHandle | str,
        source: str | None = None
    ) -> "UserCurrLog":
        """创建钻石变动日志

        参数:
            user_id: 用户ID
            diamond: 钻石数量
            handle: 货币处理类型
            source: 来源

        返回:
            UserCurrLog: 创建的日志记录
        """
        handle_value = handle.value if isinstance(handle, CurrHandle) else handle
        return await cls.create(
            user_id=user_id,
            diamond=diamond,
            handle=handle_value,
            source=source,
            db_name="log_db"
        )

    @classmethod
    async def create_xingqiong_log(
        cls,
        user_id: str,
        xingqiong: int,
        handle: CurrHandle | str,
        source: str | None = None
    ) -> "UserCurrLog":
        """创建星琼变动日志

        参数:
            user_id: 用户ID
            xingqiong: 星琼数量
            handle: 货币处理类型
            source: 来源

        返回:
            UserCurrLog: 创建的日志记录
        """
        handle_value = handle.value if isinstance(handle, CurrHandle) else handle
        return await cls.create(
            user_id=user_id,
            xingqiong=xingqiong,
            handle=handle_value,
            source=source,
            db_name="log_db"
        )

    @classmethod
    async def create_yuanshi_log(
        cls,
        user_id: str,
        yuanshi: int,
        handle: CurrHandle | str,
        source: str | None = None
    ) -> "UserCurrLog":
        """创建原石变动日志

        参数:
            user_id: 用户ID
            yuanshi: 原石数量
            handle: 货币处理类型
            source: 来源

        返回:
            UserCurrLog: 创建的日志记录
        """
        handle_value = handle.value if isinstance(handle, CurrHandle) else handle
        return await cls.create(
            user_id=user_id,
            yuanshi=yuanshi,
            handle=handle_value,
            source=source,
            db_name="log_db"
        )

    @classmethod
    async def create_tianrew_log(
        cls,
        user_id: str,
        tianrew: int,
        handle: CurrHandle | str,
        source: str | None = None
    ) -> "UserCurrLog":
        """创建天赏点变动日志

        参数:
            user_id: 用户ID
            tianrew: 天赏点数量
            handle: 货币处理类型
            source: 来源

        返回:
            UserCurrLog: 创建的日志记录
        """
        handle_value = handle.value if isinstance(handle, CurrHandle) else handle
        return await cls.create(
            user_id=user_id,
            tianrew=tianrew,
            handle=handle_value,
            source=source,
            db_name="log_db"
        )
