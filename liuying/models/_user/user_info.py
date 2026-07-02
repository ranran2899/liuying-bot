"""用户信息模型"""

from datetime import datetime

from sqlalchemy import BigInteger, String, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model
from liuying.utils.enum import CurrHandle, CacheType
from liuying.utils.exception import InsufficientGold

from .._log.user_curr_log import UserCurrLog

class UserInfo(Model):
    """用户信息模型类"""

    __tablename__ = "user_info"
    __table_args__ = {"comment": "用户信息表，用于管理用户的基本信息"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="自增id")
    """自增id"""
    user_id: Mapped[str] = mapped_column(String(255), unique=True, comment="用户ID")
    """用户ID"""
    uid: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True, comment="用户uid")
    """用户uid"""
    uid_token: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="uid令牌")
    """uid令牌"""
    gold: Mapped[int] = mapped_column(BigInteger, default=0, comment="金币数量")
    """金币数量"""
    favor_value: Mapped[int] = mapped_column(default=0, comment="好感度等级")
    """好感度等级"""
    level_value: Mapped[int] = mapped_column(default=0, comment="用户等级")
    """用户等级"""
    platform: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="平台")
    """平台"""
    items: Mapped[str] = mapped_column(Text, default="{}", comment="用户道具，JSON格式存储")
    """用户道具，JSON格式存储"""
    create_time: Mapped[datetime] = mapped_column(default=datetime.now, comment="创建时间")
    """创建时间"""

    cache_type = CacheType.USERS
    """缓存类型"""
    cache_key_field = "user_id"
    """缓存键字段"""

    @classmethod
    async def get_user(cls, user_id: str, platform: str | None = None) -> "UserInfo":
        """获取用户

        参数:
            user_id: 用户id
            platform: 平台.

        返回:
            UserInfo: UserInfo
        """
        if not await cls.filter(user_id=user_id).exists():
            await cls.create(user_id=user_id, platform=platform, uid=await cls.get_new_uid())
        return await cls.filter(user_id=user_id).first()

    @classmethod
    async def get_user_gold(cls, user_id: str) -> int:
        """
        获取用户金币

        参数:
            user_id: 用户ID

        返回:
            int: 用户当前金币数量
        """
        user, _ = await cls.get_or_create(user_id=str(user_id))
        return user.gold

    @classmethod
    async def get_user_uid(cls, user_id: str) -> str:
        """
        获取用户UID，如果UID为空则自动创建新的UID

        参数:
            user_id: 用户ID

        返回:
            str: 用户UID
        """
        user, _ = await cls.get_or_create(user_id=str(user_id))

        if not user.uid:
            max_uid = await cls.filter().where_not_null("uid").max("uid")
            if max_uid:
                new_uid = str(int(max_uid) + 1)
            else:
                new_uid = "100000001"
            user.uid = new_uid
            await user.save()
        return user.uid

    @classmethod
    async def get_new_uid(cls) -> str:
        """
        获取最新UID

        返回:
            str: 最新UID
        """
        user = await cls.filter().where_not_null("uid").order_by(text("uid DESC")).first()
        if user:
            return str(int(user.uid) + 1)
        return "100000001"

    @classmethod
    async def set_uid_token(cls, uid: str, token: str) -> str:
        """
        设置UID令牌

        参数:
            uid: 用户唯一标识
            token: 设置的令牌字符串
        返回:
            str: UID当前令牌字符串
        """
        user, _ = await cls.get_or_create(uid=uid)
        user.uid_token = token
        await user.save()
        return user.uid_token

    @classmethod
    async def get_uid_token(cls, uid: str) -> str:
        """
        根据UID获取UID令牌

        参数:
            uid: 用户唯一标识

        返回:
            str: UID对应的令牌字符串，如果没有令牌则返回空字符串
        """
        user = await cls.filter(uid=uid).first()
        if user and user.uid_token:
            return user.uid_token
        return ""

    @classmethod
    async def add_gold(
        cls,
        user_id: str,
        gold: int,
        source: str | None = None,
        platform: str | None = None,
    ):
        """添加金币

        参数:
            user_id: 用户id
            gold: 金币
            source: 插件模块
            platform: 平台.
        """
        user, _ = await cls.get_or_create(
            user_id=user_id,
            defaults={"platform": platform, "uid": await cls.get_new_uid()},
        )
        user.gold += gold
        await user.save(update_fields=["gold"])
        await UserCurrLog.create_gold_log(  
            user_id=user_id, gold=gold, handle=CurrHandle.GET, source=source
        )

    @classmethod
    async def reduce_gold(
        cls,
        user_id: str,
        gold: int,
        source: str | None = None,
        platform: str | None = None,
    ):
        """消耗金币

        参数:
            user_id: 用户id
            gold: 金币
            source: 插件模块
            platform: 平台.

        异常:
            InsufficientGold: 金币不足
        """
        user, _ = await cls.get_or_create(
            user_id=user_id,
            defaults={"platform": platform, "uid": await cls.get_new_uid()},
        )
        if user.gold < gold:
            raise InsufficientGold()
        user.gold -= gold
        await user.save(update_fields=["gold"])
        await UserCurrLog.create_gold_log(
            user_id=user_id, gold=gold, handle=CurrHandle.PLUGIN, source=source
        )

    @classmethod
    def _run_script(cls):
        """添加items字段和uid_token并移除unique约束"""
        return [
            "ALTER TABLE user_info ADD items TEXT DEFAULT '{}';",
            "ALTER TABLE user_info ADD uid_token Text DEFAULT '';",
            "DROP INDEX IF EXISTS ix_user_info_uid_token;",
            "DROP INDEX IF EXISTS user_info_uid_token_key;",
        ]
