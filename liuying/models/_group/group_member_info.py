import asyncio
from datetime import datetime
from typing import ClassVar

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.data_access import DataAccess
from liuying.services.liuying_db import Model
from liuying.utils.enum import CacheType, DbLockType


class GroupInfoUser(Model):
    """群员信息模型类

    用于存储和管理群员信息数据
    """

    __tablename__ = "group_member_info"
    __table_args__: ClassVar[dict[str, str]] = {"comment": "群员信息数据表"}

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    """自增id"""
    user_id: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="用户id"
    )
    """用户id"""
    user_name: Mapped[str] = mapped_column(
        String(255), default="", comment="用户昵称"
    )
    """用户昵称"""
    group_id: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="群聊id"
    )
    """群聊id"""
    nickname: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="群聊昵称"
    )
    """群聊昵称"""
    uid: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="用户uid"
    )
    """用户uid"""
    user_join_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="用户入群时间"
    )
    """用户入群时间"""
    platform: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="平台"
    )
    """平台"""

    cache_type: ClassVar[CacheType] = CacheType.USERS
    """缓存类型"""
    cache_key_field: ClassVar[tuple[str, str]] = ("user_id", "group_id")
    """缓存键字段"""
    enable_lock: ClassVar[list[DbLockType]] = [DbLockType.CREATE, DbLockType.UPSERT]
    """启用锁类型"""

    @classmethod
    async def get_all_uid(cls, group_id: str) -> set[str]:
        """获取该群所有用户id

        参数:
            group_id: 群号

        返回:
            set[str]: 用户id集合
        """
        results = await cls.filter(group_id=group_id).values("user_id")
        return {result.user_id for result in results}

    @classmethod
    async def set_user_nickname(
        cls,
        user_id: str,
        group_id: str,
        nickname: str,
        user_name: str | None = None,
        platform: str | None = None,
    ):
        """设置群员在该群内的昵称

        参数:
            user_id: 用户id
            group_id: 群号
            nickname: 昵称
            user_name: 用户昵称
            platform: 平台
        """
        defaults = {"nickname": nickname}
        if user_name is not None:
            defaults["user_name"] = user_name
        if platform is not None:
            defaults["platform"] = platform

        await cls.update_or_create(
            user_id=user_id,
            group_id=group_id,
            defaults=defaults,
        )

    @classmethod
    async def get_user_all_group(cls, user_id: str) -> list[str]:
        """获取该用户所在的所有群聊

        参数:
            user_id: 用户id

        返回:
            list[str]: 群聊id列表
        """
        results = await cls.filter(user_id=user_id).values("group_id")
        return [result.group_id for result in results]

    @classmethod
    async def get_user_nickname(cls, user_id: str, group_id: str) -> str:
        """获取用户在该群的昵称

        参数:
            user_id: 用户id
            group_id: 群号

        返回:
            str: 用户昵称，如果不存在则返回空字符串
        """
        if user := await cls.filter(user_id=user_id, group_id=group_id).first():
            return user.nickname or ""
        return ""

    @classmethod
    async def update_user_info(
        cls,
        user_id: str,
        group_id: str,
        user_name: str | None = None,
        user_join_time: datetime | None = None,
        nickname: str | None = None,
        uid: int | None = None,
        platform: str | None = None,
    ):
        """更新用户信息

        参数:
            user_id: 用户id
            group_id: 群号
            user_name: 用户昵称
            user_join_time: 用户入群时间
            nickname: 群聊昵称
            uid: 用户uid
            platform: 平台
        """
        defaults = {}
        if user_name is not None:
            defaults["user_name"] = user_name
        if user_join_time is not None:
            defaults["user_join_time"] = user_join_time
        if nickname is not None:
            defaults["nickname"] = nickname
        if uid is not None:
            defaults["uid"] = uid
        if platform is not None:
            defaults["platform"] = platform

        await cls.update_or_create(
            user_id=user_id,
            group_id=group_id,
            defaults=defaults,
        )

    @classmethod
    async def batch_update_user_name(cls, users: list["GroupInfoUser"]) -> None:
        """批量更新用户昵称并清除缓存

        参数:
            users: 要更新的群员列表
        """
        if not users:
            return
        await cls.filter().bulk_update(users, ["user_name"])
        dao = DataAccess(cls)
        await asyncio.gather(
            *(
                dao.clear_cache(user_id=user.user_id, group_id=user.group_id)
                for user in users
            )
        )

    @classmethod
    async def delete_by_ids(cls, ids: list[int]) -> None:
        """根据自增id列表删除群员并清除缓存

        参数:
            ids: 自增id列表
        """
        if not ids:
            return
        users = await cls.filter(cls.id.in_(ids)).all()
        if not users:
            return
        dao = DataAccess(cls)
        await asyncio.gather(
            *(
                dao.clear_cache(user_id=user.user_id, group_id=user.group_id)
                for user in users
            )
        )
        await cls.filter(cls.id.in_(ids)).delete()

    @classmethod
    async def delete_members(cls, user_ids: list[str], group_id: str) -> None:
        """批量删除群员并清除缓存

        参数:
            user_ids: 用户id列表
            group_id: 群聊id
        """
        if not user_ids:
            return
        dao = DataAccess(cls)
        await asyncio.gather(
            *(
                dao.clear_cache(user_id=user_id, group_id=group_id)
                for user_id in user_ids
            )
        )
        await cls.filter(cls.user_id.in_(user_ids), cls.group_id == group_id).delete()

    @classmethod
    def _run_script(cls):
        """数据库迁移脚本

        返回:
            list: SQL语句列表，用于数据库表结构更新
        """
        return [
            "ALTER TABLE group_member_info "
            "ALTER COLUMN user_join_time DROP NOT NULL;",
            "ALTER TABLE group_member_info ALTER COLUMN uid TYPE BIGINT;",
            "ALTER TABLE group_member_info "
            "ADD COLUMN platform VARCHAR(255) default 'qq';",
        ]
