"""用户其他货币"""

from sqlalchemy import String, BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model
from liuying.utils.enum import CurrHandle
from liuying.utils.exception import (
    InsufficientCopper,
    InsufficientSilver,
    InsufficientDiamond,
    InsufficientXingqiong,
    InsufficientYuanshi,
    InsufficientTianrew,
)

from .._log.user_curr_log import UserCurrLog


class UserCurr(Model):
    """用户其他货币模型类"""

    __tablename__ = "user_curr"
    __table_args__ = {"comment": "用户其他货币表"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="自增id")
    """自增id"""
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True, comment="用户id")
    """用户id"""
    copper: Mapped[int] = mapped_column(BigInteger, default=0, comment="铜币数量")
    """铜币数量"""
    silver: Mapped[int] = mapped_column(BigInteger, default=0, comment="银币数量")
    """银币数量"""
    diamond: Mapped[int] = mapped_column(BigInteger, default=0, comment="钻石数量")
    """钻石数量"""
    xingqiong: Mapped[int] = mapped_column(BigInteger, default=0, comment="星琼数量")
    """星琼数量"""
    yuanshi: Mapped[int] = mapped_column(BigInteger, default=0, comment="原石数量")
    """原石数量"""
    tianrew: Mapped[int] = mapped_column(BigInteger, default=0, comment="天赏点数量")
    """天赏点数量"""
    platform: Mapped[str | None] = mapped_column(String(255), comment="平台")
    """平台"""

    @classmethod
    async def get_user_copper(cls, user_id: str) -> int:
        """获取用户铜币

        参数:
            user_id: 用户ID

        返回:
            int: 用户当前铜币数量
        """
        user, _ = await cls.get_or_create(user_id=str(user_id))
        return user.copper

    @classmethod
    async def add_copper(
        cls,
        user_id: str,
        copper: int,
        source: str | None = None,
        platform: str | None = None,
    ):
        """添加铜币

        参数:
            user_id: 用户id
            copper: 铜币数量
            source: 来源
            platform: 平台
        """
        user, _ = await cls.get_or_create(
            user_id=user_id, defaults={"platform": platform}
        )
        user.copper += copper
        await user.save(update_fields=["copper"])
        await UserCurrLog.create_copper_log(
            user_id=user_id, copper=copper, handle=CurrHandle.GET, source=source
        )

    @classmethod
    async def reduce_copper(
        cls,
        user_id: str,
        copper: int,
        source: str | None = None,
        platform: str | None = None,
    ):
        """消耗铜币

        参数:
            user_id: 用户id
            copper: 铜币数量
            source: 来源
            platform: 平台

        异常:
            InsufficientCopper: 铜币不足
        """
        user, _ = await cls.get_or_create(
            user_id=user_id, defaults={"platform": platform}
        )
        if user.copper < copper:
            raise InsufficientCopper()
        user.copper -= copper
        await user.save(update_fields=["copper"])
        await UserCurrLog.create_copper_log(
            user_id=user_id, copper=copper, handle=CurrHandle.PLUGIN, source=source
        )

    @classmethod
    async def get_user_silver(cls, user_id: str) -> int:
        """获取用户银币

        参数:
            user_id: 用户ID

        返回:
            int: 用户当前银币数量
        """
        user, _ = await cls.get_or_create(user_id=str(user_id))
        return user.silver

    @classmethod
    async def add_silver(
        cls,
        user_id: str,
        silver: int,
        source: str | None = None,
        platform: str | None = None,
    ):
        """添加银币

        参数:
            user_id: 用户id
            silver: 银币数量
            source: 来源
            platform: 平台
        """
        user, _ = await cls.get_or_create(
            user_id=user_id, defaults={"platform": platform}
        )
        user.silver += silver
        await user.save(update_fields=["silver"])
        await UserCurrLog.create_silver_log(
            user_id=user_id, silver=silver, handle=CurrHandle.GET, source=source
        )

    @classmethod
    async def reduce_silver(
        cls,
        user_id: str,
        silver: int,
        source: str | None = None,
        platform: str | None = None,
    ):
        """消耗银币

        参数:
            user_id: 用户id
            silver: 银币数量
            source: 来源
            platform: 平台

        异常:
            InsufficientSilver: 银币不足
        """
        user, _ = await cls.get_or_create(
            user_id=user_id, defaults={"platform": platform}
        )
        if user.silver < silver:
            raise InsufficientSilver()
        user.silver -= silver
        await user.save(update_fields=["silver"])
        await UserCurrLog.create_silver_log(
            user_id=user_id, silver=silver, handle=CurrHandle.PLUGIN, source=source
        )

    @classmethod
    async def get_user_diamond(cls, user_id: str) -> int:
        """获取用户钻石

        参数:
            user_id: 用户ID

        返回:
            int: 用户当前钻石数量
        """
        user, _ = await cls.get_or_create(user_id=str(user_id))
        return user.diamond

    @classmethod
    async def add_diamond(
        cls,
        user_id: str,
        diamond: int,
        source: str | None = None,
        platform: str | None = None,
    ):
        """添加钻石

        参数:
            user_id: 用户id
            diamond: 钻石数量
            source: 来源
            platform: 平台
        """
        user, _ = await cls.get_or_create(
            user_id=user_id, defaults={"platform": platform}
        )
        user.diamond += diamond
        await user.save(update_fields=["diamond"])
        await UserCurrLog.create_diamond_log(
            user_id=user_id, diamond=diamond, handle=CurrHandle.GET, source=source
        )

    @classmethod
    async def reduce_diamond(
        cls,
        user_id: str,
        diamond: int,
        source: str | None = None,
        platform: str | None = None,
    ):
        """消耗钻石

        参数:
            user_id: 用户id
            diamond: 钻石数量
            source: 来源
            platform: 平台

        异常:
            InsufficientDiamond: 钻石不足
        """
        user, _ = await cls.get_or_create(
            user_id=user_id, defaults={"platform": platform}
        )
        if user.diamond < diamond:
            raise InsufficientDiamond()
        user.diamond -= diamond
        await user.save(update_fields=["diamond"])
        await UserCurrLog.create_diamond_log(
            user_id=user_id, diamond=diamond, handle=CurrHandle.PLUGIN, source=source
        )

    @classmethod
    async def get_user_xingqiong(cls, user_id: str) -> int:
        """获取用户星琼

        参数:
            user_id: 用户ID

        返回:
            int: 用户当前星琼数量
        """
        user, _ = await cls.get_or_create(user_id=str(user_id))
        return user.xingqiong

    @classmethod
    async def add_xingqiong(
        cls,
        user_id: str,
        xingqiong: int,
        source: str | None = None,
        platform: str | None = None,
    ):
        """添加星琼

        参数:
            user_id: 用户id
            xingqiong: 星琼数量
            source: 来源
            platform: 平台
        """
        user, _ = await cls.get_or_create(
            user_id=user_id, defaults={"platform": platform}
        )
        user.xingqiong += xingqiong
        await user.save(update_fields=["xingqiong"])
        await UserCurrLog.create_xingqiong_log(
            user_id=user_id, xingqiong=xingqiong, handle=CurrHandle.GET, source=source
        )

    @classmethod
    async def reduce_xingqiong(
        cls,
        user_id: str,
        xingqiong: int,
        source: str | None = None,
        platform: str | None = None,
    ):
        """消耗星琼

        参数:
            user_id: 用户id
            xingqiong: 星琼数量
            source: 来源
            platform: 平台

        异常:
            InsufficientXingqiong: 星琼不足
        """
        user, _ = await cls.get_or_create(
            user_id=user_id, defaults={"platform": platform}
        )
        if user.xingqiong < xingqiong:
            raise InsufficientXingqiong()
        user.xingqiong -= xingqiong
        await user.save(update_fields=["xingqiong"])
        await UserCurrLog.create_xingqiong_log(
            user_id=user_id, xingqiong=xingqiong, handle=CurrHandle.PLUGIN, source=source
        )

    @classmethod
    async def get_user_yuanshi(cls, user_id: str) -> int:
        """获取用户原石

        参数:
            user_id: 用户ID

        返回:
            int: 用户当前原石数量
        """
        user, _ = await cls.get_or_create(user_id=str(user_id))
        return user.yuanshi

    @classmethod
    async def add_yuanshi(
        cls,
        user_id: str,
        yuanshi: int,
        source: str | None = None,
        platform: str | None = None,
    ):
        """添加原石

        参数:
            user_id: 用户id
            yuanshi: 原石数量
            source: 来源
            platform: 平台
        """
        user, _ = await cls.get_or_create(
            user_id=user_id, defaults={"platform": platform}
        )
        user.yuanshi += yuanshi
        await user.save(update_fields=["yuanshi"])
        await UserCurrLog.create_yuanshi_log(
            user_id=user_id, yuanshi=yuanshi, handle=CurrHandle.GET, source=source
        )

    @classmethod
    async def reduce_yuanshi(
        cls,
        user_id: str,
        yuanshi: int,
        source: str | None = None,
        platform: str | None = None,
    ):
        """消耗原石

        参数:
            user_id: 用户id
            yuanshi: 原石数量
            source: 来源
            platform: 平台

        异常:
            InsufficientYuanshi: 原石不足
        """
        user, _ = await cls.get_or_create(
            user_id=user_id, defaults={"platform": platform}
        )
        if user.yuanshi < yuanshi:
            raise InsufficientYuanshi()
        user.yuanshi -= yuanshi
        await user.save(update_fields=["yuanshi"])
        await UserCurrLog.create_yuanshi_log(
            user_id=user_id, yuanshi=yuanshi, handle=CurrHandle.PLUGIN, source=source
        )

    @classmethod
    async def get_user_tianrew(cls, user_id: str) -> int:
        """获取用户天赏点

        参数:
            user_id: 用户ID

        返回:
            int: 用户当前天赏点数量
        """
        user, _ = await cls.get_or_create(user_id=str(user_id))
        return user.tianrew

    @classmethod
    async def add_tianrew(
        cls,
        user_id: str,
        tianrew: int,
        source: str | None = None,
        platform: str | None = None,
    ):
        """添加天赏点

        参数:
            user_id: 用户id
            tianrew: 天赏点数量
            source: 来源
            platform: 平台
        """
        user, _ = await cls.get_or_create(
            user_id=user_id, defaults={"platform": platform}
        )
        user.tianrew += tianrew
        await user.save(update_fields=["tianrew"])
        await UserCurrLog.create_tianrew_log(
            user_id=user_id, tianrew=tianrew, handle=CurrHandle.GET, source=source
        )

    @classmethod
    async def reduce_tianrew(
        cls,
        user_id: str,
        tianrew: int,
        source: str | None = None,
        platform: str | None = None,
    ):
        """消耗天赏点

        参数:
            user_id: 用户id
            tianrew: 天赏点数量
            source: 来源
            platform: 平台

        异常:
            InsufficientTianrew: 天赏点不足
        """
        user, _ = await cls.get_or_create(
            user_id=user_id, defaults={"platform": platform}
        )
        if user.tianrew < tianrew:
            raise InsufficientTianrew()
        user.tianrew -= tianrew
        await user.save(update_fields=["tianrew"])
        await UserCurrLog.create_tianrew_log(
            user_id=user_id, tianrew=tianrew, handle=CurrHandle.PLUGIN, source=source
        )
