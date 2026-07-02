"""机器人好友模型类"""

from typing import ClassVar

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from liuying.configs.config import Config
from liuying.services.liuying_db import Model
from liuying.utils.enum import CacheType


class BotFriend(Model):
    """机器人好友模型类

    用于存储和管理机器人的好友用户信息,支持多机器人隔离
    """

    __tablename__ = "bot_friends"
    __table_args__: ClassVar[tuple] = (
        UniqueConstraint("bot_id", "user_id"),
        {"comment": "机器人好友信息数据表"},
    )

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    """自增id"""
    bot_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="机器人ID"
    )
    """机器人ID - 所属机器人标识"""
    user_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="用户id"
    )
    """用户id"""
    user_name: Mapped[str] = mapped_column(
        String(255), default="", comment="用户名称"
    )
    """用户名称"""
    nickname: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="用户自定义昵称"
    )
    """私聊下自定义昵称"""
    platform: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="平台"
    )
    """平台"""

    cache_type = CacheType.BOT
    """缓存类型"""
    cache_key_field = ("bot_id", "user_id")
    """缓存键字段 - 复合键"""

    @classmethod
    async def get_user_name(cls, bot_id: str, user_id: str) -> str:
        """获取好友用户名称

        参数:
            bot_id: 机器人ID
            user_id: 用户id

        返回:
            str: 用户名称，如果不存在则返回空字符串
        """
        user = await cls.filter(bot_id=bot_id, user_id=user_id).first()
        return user.user_name if user else ""

    @classmethod
    async def get_user_nickname(cls, bot_id: str, user_id: str) -> str:
        """获取用户昵称

        参数:
            bot_id: 机器人ID
            user_id: 用户id

        返回:
            str: 用户昵称，如果不存在则返回空字符串
        """
        user = await cls.filter(bot_id=bot_id, user_id=user_id).first()

        if user and user.nickname:
            _tmp = ""
            if black_word := Config.get_config("nickname", "BLACK_WORD") or "baba":
                for x in user.nickname:
                    _tmp += "*" if x in black_word else x
            else:
                _tmp = user.nickname
            return _tmp
        return ""

    @classmethod
    async def set_user_nickname(
        cls,
        bot_id: str,
        user_id: str,
        nickname: str,
        uname: str | None = None,
        platform: str | None = None,
    ) -> tuple["BotFriend", bool]:
        """设置用户昵称

        参数:
            bot_id: 机器人ID
            user_id: 用户id
            nickname: 昵称
            uname: 用户名称
            platform: 平台

        返回:
            tuple[BotFriend, bool]: 模型实例和是否为新创建的布尔值
        """
        defaults = {"nickname": nickname}
        if uname is not None:
            defaults["user_name"] = uname
        if platform is not None:
            defaults["platform"] = platform

        return await cls.update_or_create(
            bot_id=bot_id,
            user_id=user_id,
            defaults=defaults,
        )

    @classmethod
    async def get_friends(cls, bot_id: str) -> list["BotFriend"]:
        """获取机器人的所有好友

        参数:
            bot_id: 机器人ID

        返回:
            list[BotFriend]: 好友列表
        """
        return await cls.filter(bot_id=bot_id).all()

    @classmethod
    async def is_friend(cls, bot_id: str, user_id: str) -> bool:
        """检查用户是否为机器人好友

        参数:
            bot_id: 机器人ID
            user_id: 用户id

        返回:
            bool: 是否为好友
        """
        return await cls.filter(bot_id=bot_id, user_id=user_id).exists()

    @classmethod
    async def delete_friend(cls, bot_id: str, user_id: str) -> bool:
        """删除机器人好友

        参数:
            bot_id: 机器人ID
            user_id: 用户id

        返回:
            bool: 是否删除成功
        """
        friend = await cls.filter(bot_id=bot_id, user_id=user_id).first()
        if not friend:
            return False
        await friend.delete()
        return True

    # @classmethod
    # def _run_script(cls):
    #     """数据库迁移

    #     返回:
    #         list: SQL语句列表，用于数据库表结构更新
    #     """
    #     return [
    #         "ALTER TABLE bot_friends "
    #         "ALTER COLUMN user_id TYPE VARCHAR(255);",
    #     ]
