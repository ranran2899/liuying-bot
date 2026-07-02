""" 用户介绍模型类 """

from typing import ClassVar

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model
from liuying.utils.enum import CacheType


class UserIntroInfo(Model):
    """用户介绍模型类"""

    __tablename__ = "user_intro"
    __table_args__: ClassVar[dict[str, str]] = {
        "comment": "用户介绍表，用于管理用户的介绍信息"
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    """自增id"""
    user_id: Mapped[str] = mapped_column(String(255), index=True, comment="用户id")
    """用户id"""
    nickname: Mapped[str] = mapped_column(String(255), default="", comment="用户昵称")
    """用户昵称"""
    avatar: Mapped[str] = mapped_column(String(500), default="", comment="用户头像url")
    """用户头像url"""
    title: Mapped[str] = mapped_column(String(255), default="", comment="用户称号")
    """用户称号"""
    signature: Mapped[str] = mapped_column(
        String(500), default="", comment="用户签名或介绍"
    )
    """用户签名或介绍"""
    gender: Mapped[str] = mapped_column(String(255), default="未知", comment="用户性别")
    """用户性别"""
    age: Mapped[int] = mapped_column(default=0, comment="用户年龄")
    """用户年龄"""
    location: Mapped[str] = mapped_column(
        String(255), default="北京", comment="用户位置"
    )
    """用户位置"""
    platform: Mapped[str | None] = mapped_column(
        String(255), default="", comment="用户所在平台"
    )
    """用户所在平台"""

    cache_type = CacheType.USERS
    """缓存类型"""
    cache_key_field = ("user_id", "nickname", "avatar")
    """缓存键字段"""

    @classmethod
    async def get_nickname(cls, user_id: str) -> str:
        """
        获取用户昵称

        参数:
            user_id: 用户ID

        返回:
            str: 用户昵称，如果用户不存在则返回空字符串
        """
        user = await cls.safe_get_or_none(user_id=user_id)
        return user.nickname if user else ""

    @classmethod
    async def set_nickname(cls, user_id: str, nickname: str) -> bool:
        """
        设置用户昵称

        参数:
            user_id: 用户ID
            nickname: 要设置的用户昵称

        返回:
            bool: 设置成功返回True，失败返回False
        """
        user, _ = await cls.get_or_create(user_id=user_id)
        user.nickname = nickname
        await user.save(update_fields=["nickname"])
        return True

    @classmethod
    async def get_avatar(cls, user_id: str) -> str:
        """
        获取用户头像

        参数:
            user_id: 用户ID

        返回:
            str: 用户头像，如果用户不存在则返回空字符串
        """
        user = await cls.safe_get_or_none(user_id=user_id)
        return user.avatar if user else ""

    @classmethod
    async def set_avatar(cls, user_id: str, avatar: str) -> bool:
        """
        设置用户头像

        参数:
            user_id: 用户ID
            avatar: 要设置的用户头像

        返回:
            bool: 设置成功返回True，失败返回False
        """
        user, _ = await cls.get_or_create(user_id=user_id)
        user.avatar = avatar
        await user.save(update_fields=["avatar"])
        return True

    @classmethod
    async def set_platform(cls, user_id: str, platform: str | None = None) -> bool:
        """
        设置用户所在平台

        参数:
            user_id: 用户ID
            platform: 要设置的用户所在平台

        返回:
            bool: 设置成功返回True，失败返回False
        """
        user, _ = await cls.get_or_create(user_id=user_id)
        user.platform = platform
        await user.save(update_fields=["platform"])
        return True

    @classmethod
    async def get_location(cls, user_id: str) -> str:
        """
        获取用户位置

        参数:
            user_id: 用户ID

        返回:
            str: 用户位置，如果用户不存在则返回默认值'北京'
        """
        user = await cls.safe_get_or_none(user_id=user_id)
        return user.location if user else "北京"


    @classmethod
    def _run_script(cls):
        """
        数据库迁移

        返回:
            list: SQL语句列表，用于数据库表结构更新
        """
        return [
            "ALTER TABLE user_intro "
            "ADD COLUMN avatar VARCHAR(500) DEFAULT '' COMMENT '用户头像'",
            "ALTER TABLE user_intro "
            "ADD COLUMN platform VARCHAR(255) DEFAULT '' COMMENT '用户所在平台'",
        ]
