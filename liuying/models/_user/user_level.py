"""用户权限等级模型类"""

import nonebot
from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from liuying.configs.config import BotConfig
from liuying.services.liuying_db import Model
from liuying.utils.enum import CacheType


class UserLevel(Model):
    """
    用户权限等级模型类

    用于管理用户的权限等级，支持三种权限类型：
    1. 全局用户权限：bot_id=None, group_id=None
    2. 群组用户权限：bot_id=None, group_id=xxx
    3. 机器人用户权限：bot_id=xxx, group_id=None

    支持记录用户所在平台，超级用户默认返回 10 级。
    """

    __tablename__ = "level_user"
    __table_args__ = (
        UniqueConstraint("user_id", "group_id", "bot_id"),
        {"comment": "用户权限等级表，用于管理用户的权限等级"},
    )

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    """自增id"""
    user_id: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="用户id"
    )
    """用户id"""
    group_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="群聊id"
    )
    """群聊id"""
    bot_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="机器人id"
    )
    """机器人id"""
    platform: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="用户所在平台"
    )
    """用户所在平台"""
    user_level: Mapped[int] = mapped_column(
        nullable=False, comment="用户权限等级"
    )
    """用户权限等级"""
    group_flag: Mapped[int] = mapped_column(
        default=0,
        comment="特殊标记，是否随群管理员变更而设置权限",
    )
    """特殊标记，是否随群管理员变更而设置权限"""

    cache_type = CacheType.LEVEL
    """缓存类型"""
    cache_key_field = ("user_id", "group_id", "bot_id")
    """缓存键字段"""

    @classmethod
    def _is_superuser(cls, user_id: str, platform: str | None = None) -> bool:
        """
        检查用户是否为超级用户

        优先检查 NoneBot 全局超级用户，再检查平台超级用户配置。

        参数:
            user_id: 用户id
            platform: 平台名称

        返回:
            bool: 是否为超级用户
        """
        if user_id in nonebot.get_driver().config.superusers:
            return True
        if platform and user_id in BotConfig.get_superuser(platform):
            return True
        return False

    @classmethod
    async def _fetch_level(
        cls,
        user_id: str,
        group_id: str | None = None,
        bot_id: str | None = None,
    ) -> int:
        """
        内部方法：获取指定条件的权限等级

        参数:
            user_id: 用户id
            group_id: 群组id
            bot_id: 机器人id

        返回:
            int: 权限等级
        """
        query = cls.filter(user_id=user_id)
        if group_id is not None:
            query = query.filter(group_id=group_id).where_null("bot_id")
        elif bot_id is not None:
            query = query.filter(bot_id=bot_id).where_null("group_id")
        else:
            query = query.where_null("group_id").where_null("bot_id")
        user = await query.first()
        return user.user_level if user else 0

    @classmethod
    async def get_level(
        cls,
        user_id: str,
        bot_id: str | None = None,
        group_id: str | None = None,
        platform: str | None = None,
    ) -> int:
        """
        获取用户综合权限等级（取各级别最大值）

        权限判定优先级：
        1. 全局用户权限
        2. 机器人用户权限
        3. 群中用户权限

        超级用户直接返回 10 级。

        参数:
            user_id: 用户id
            bot_id: 机器人id
            group_id: 群组id
            platform: 平台名称

        返回:
            int: 权限等级
        """
        if cls._is_superuser(user_id, platform):
            return 10
        levels = [await cls._fetch_level(user_id, None, None)]
        if bot_id:
            levels.append(await cls._fetch_level(user_id, None, bot_id))
        if group_id:
            levels.append(await cls._fetch_level(user_id, group_id, None))
        return max(levels)

    @classmethod
    async def get_user_level(
        cls,
        user_id: str,
        group_id: str | None = None,
        platform: str | None = None,
    ) -> int:
        """
        获取用户权限等级（兼容旧接口）

        参数:
            user_id: 用户id
            group_id: 群组id
            platform: 平台名称

        返回:
            int: 权限等级
        """
        if cls._is_superuser(user_id, platform):
            return 10
        return await cls._fetch_level(user_id, group_id, None)

    @classmethod
    async def get_bot_level(
        cls, bot_id: str, user_id: str, platform: str | None = None
    ) -> int:
        """
        获取用户在指定机器人上的权限等级

        参数:
            bot_id: 机器人id
            user_id: 用户id
            platform: 平台名称

        返回:
            int: 权限等级
        """
        if cls._is_superuser(user_id, platform):
            return 10
        return await cls._fetch_level(user_id, None, bot_id)

    @classmethod
    async def set_level(
        cls,
        user_id: str,
        group_id: str | None = None,
        level: int = 0,
        group_flag: int = 0,
        platform: str | None = None,
    ):
        """
        设置用户权限

        参数:
            user_id: 用户id
            group_id: 群组id
            level: 权限等级
            group_flag: 是否被自动更新刷新权限 0:是, 1:否
            platform: 平台名称
        """
        user, _ = await cls.update_or_create(
            user_id=user_id,
            group_id=group_id,
            bot_id=None,
            defaults={"user_level": level, "group_flag": group_flag},
        )
        if platform and user.platform != platform:
            user.platform = platform
            await user.save(update_fields=["platform"])

    @classmethod
    async def set_bot_level(
        cls,
        bot_id: str,
        user_id: str,
        level: int = 0,
        platform: str | None = None,
    ):
        """
        设置用户在指定机器人上的权限

        参数:
            bot_id: 机器人id
            user_id: 用户id
            level: 权限等级
            platform: 平台名称
        """
        user, _ = await cls.update_or_create(
            user_id=user_id,
            bot_id=bot_id,
            group_id=None,
            defaults={"user_level": level, "group_flag": 0},
        )
        if platform and user.platform != platform:
            user.platform = platform
            await user.save(update_fields=["platform"])

    @classmethod
    async def delete_level(
        cls,
        user_id: str,
        group_id: str | None = None,
        platform: str | None = None,
    ) -> bool:
        """
        删除用户权限

        参数:
            user_id: 用户id
            group_id: 群组id
            platform: 平台名称

        返回:
            bool: 是否删除成功
        """
        query = cls.filter(user_id=user_id, group_id=group_id).where_null("bot_id")
        user = await query.first()
        if user:
            await user.delete()
            return True
        return False

    @classmethod
    async def delete_bot_level(
        cls, bot_id: str, user_id: str, platform: str | None = None
    ) -> bool:
        """
        删除用户在指定机器人上的权限

        参数:
            bot_id: 机器人id
            user_id: 用户id
            platform: 平台名称

        返回:
            bool: 是否删除成功
        """
        query = cls.filter(user_id=user_id, bot_id=bot_id).where_null("group_id")
        user = await query.first()
        if user:
            await user.delete()
            return True
        return False

    @classmethod
    async def check(
        cls,
        user_id: str,
        level: int,
        bot_id: str | None = None,
        group_id: str | None = None,
        platform: str | None = None,
    ) -> bool:
        """
        检查用户综合权限等级是否满足要求

        参数:
            user_id: 用户id
            level: 所需权限等级
            bot_id: 机器人id
            group_id: 群组id
            platform: 平台名称

        返回:
            bool: 是否满足权限要求
        """
        return await cls.get_level(user_id, bot_id, group_id, platform) >= level

    @classmethod
    async def check_level(
        cls,
        user_id: str,
        group_id: str | None = None,
        level: int = 0,
        platform: str | None = None,
    ) -> bool:
        """
        检查用户权限等级是否满足要求（兼容旧接口）

        参数:
            user_id: 用户id
            group_id: 群组id
            level: 权限等级
            platform: 平台名称

        返回:
            bool: 是否满足权限要求
        """
        if cls._is_superuser(user_id, platform):
            return True
        if group_id:
            return await cls._fetch_level(user_id, group_id, None) >= level
        query = cls.filter(user_id=user_id).where_null("bot_id")
        users = await query.all()
        return max((u.user_level for u in users), default=0) >= level

    @classmethod
    async def check_bot_level(
        cls,
        bot_id: str,
        user_id: str,
        level: int = 0,
        platform: str | None = None,
    ) -> bool:
        """
        检查用户在指定机器人上的权限等级是否满足要求

        参数:
            bot_id: 机器人id
            user_id: 用户id
            level: 权限等级
            platform: 平台名称

        返回:
            bool: 是否满足权限要求
        """
        return await cls.get_bot_level(bot_id, user_id, platform) >= level

    @classmethod
    async def is_group_flag(
        cls, user_id: str, group_id: str, platform: str | None = None
    ) -> bool:
        """
        检测是否会被自动更新刷新权限

        参数:
            user_id: 用户id
            group_id: 群组id
            platform: 平台名称

        返回:
            bool: 是否会被自动更新权限刷新
        """
        query = cls.filter(
            user_id=user_id,
            group_id=group_id,
        ).where_null("bot_id")
        user = await query.first()
        return user.group_flag == 1 if user else False

    @classmethod
    def _run_script(cls):
        """数据库初始化脚本"""
        return [
            "ALTER TABLE level_user ADD bot_id VARCHAR(255) DEFAULT NULL;",
            "ALTER TABLE level_user ADD platform VARCHAR(255) DEFAULT NULL;",
        ]
