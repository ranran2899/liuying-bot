"""用户媒体模型类
    只保留向后兼容的旧插件数据，不建议新项目使用
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class UserMediaInfo(Model):
    """用户媒体模型类"""

    __tablename__ = "user_media"
    __table_args__ = {"comment": "用户媒体表，用于管理用户的昵称、称号、签名、头像等媒体信息"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="自增id")
    """自增id"""
    user_id: Mapped[str] = mapped_column(String(255), index=True, comment="用户id")
    """用户id"""
    nickname: Mapped[str] = mapped_column(String(255), default="", comment="用户昵称")
    """用户昵称"""
    title: Mapped[str] = mapped_column(String(255), default="", comment="用户称号")
    """用户称号"""
    signature: Mapped[str] = mapped_column(String(500), default="", comment="用户签名或介绍")
    """用户签名或介绍"""
    avatar_path: Mapped[str] = mapped_column(String(500), default="", comment="用户头像路径")
    """用户头像路径"""
    avatar_frame_path: Mapped[str] = mapped_column(String(500), default="", comment="用户头像框路径")
    """用户头像框路径"""
    color_code: Mapped[str] = mapped_column(String(7), default="", comment="用户名称颜色代码")
    """用户名称颜色代码"""
    background_path: Mapped[str] = mapped_column(String(500), default="", comment="用户背景图片路径")
    """用户背景图片路径"""
    background_music_path: Mapped[str] = mapped_column(String(500), default="", comment="用户背景音乐路径")
    """用户背景音乐路径"""

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
        await user.save()
        return True

    @classmethod
    async def get_avatar_path(cls, user_id: str) -> str:
        """
        获取用户头像路径

        参数:
            user_id: 用户ID

        返回:
            str: 用户头像路径，如果用户不存在则返回空字符串
        """
        user = await cls.safe_get_or_none(user_id=user_id)
        return user.avatar_path if user else ""

    @classmethod
    async def set_avatar_path(cls, user_id: str, avatar_path: str) -> bool:
        """
        设置用户头像路径

        参数:
            user_id: 用户ID
            avatar_path: 要设置的用户头像路径

        返回:
            bool: 设置成功返回True，失败返回False
        """
        user, _ = await cls.get_or_create(user_id=user_id)
        user.avatar_path = avatar_path
        await user.save()
        return True
