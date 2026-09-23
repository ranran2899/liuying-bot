""" 用户介绍模型类 """

from typing import ClassVar

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


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

    @classmethod
    async def update_profile(
        cls, user_id: str, nickname: str, avatar: str, platform: str
    ) -> bool:
        """单次读写更新用户基础资料（昵称/头像/平台）

        参数:
            user_id: 用户ID
            nickname: 用户昵称
            avatar: 用户头像url
            platform: 用户所在平台

        返回:
            bool: 更新成功返回True
        """
        user, _ = await cls.get_or_create(user_id=user_id)
        user.nickname = nickname
        user.avatar = avatar
        user.platform = platform
        await user.save(update_fields=["nickname", "avatar", "platform"])
        return True

    @classmethod
    def _run_script(cls) -> list[str]:
        """数据库迁移

        返回:
            list: SQL语句列表，用于数据库表结构更新
        """
        return [
            "ALTER TABLE user_intro ADD COLUMN avatar VARCHAR(500) DEFAULT '';",
            "ALTER TABLE user_intro "
            "ADD COLUMN platform VARCHAR(255) DEFAULT '';",
        ]
