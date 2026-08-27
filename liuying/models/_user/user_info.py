"""用户信息模型"""

from datetime import datetime
from typing import ClassVar

from sqlalchemy import BigInteger, Integer, String, Text, cast
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model
from liuying.utils.enum import CacheType, CurrHandle
from liuying.utils.exception import InsufficientGold

from .._log.user_curr_log import UserCurrLog


class UserInfo(Model):
    """用户信息模型类"""

    __tablename__ = "user_info"
    __table_args__: ClassVar[dict] = {
        "comment": "用户信息表，用于管理用户的基本信息"
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    """自增id"""
    user_id: Mapped[str] = mapped_column(String(255), unique=True, comment="用户ID")
    """用户ID"""
    uid: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True, comment="用户uid"
    )
    """用户uid"""
    uid_token: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="uid令牌"
    )
    """uid令牌"""
    gold: Mapped[int] = mapped_column(BigInteger, default=0, comment="金币数量")
    """金币数量"""
    favor_value: Mapped[int] = mapped_column(default=0, comment="好感度等级")
    """好感度等级"""
    level_value: Mapped[int] = mapped_column(default=0, comment="用户等级")
    """用户等级"""
    platform: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="平台"
    )
    """平台"""
    items: Mapped[str] = mapped_column(
        Text, default="{}", comment="用户道具，JSON格式存储"
    )
    """用户道具，JSON格式存储"""
    create_time: Mapped[datetime] = mapped_column(
        default=datetime.now, comment="创建时间"
    )
    """创建时间"""

    cache_type = CacheType.USERS
    """缓存类型"""
    cache_key_field = "user_id"
    """缓存键字段"""

    @classmethod
    async def _max_uid(cls) -> str | None:
        """获取最大UID（按数值比较而非字符串字典序）"""
        return await cls.filter().where_not_null("uid").max(cast(cls.uid, Integer))

    @classmethod
    async def _new_uid(cls) -> str:
        """基于当前最大UID生成下一个UID"""
        max_uid = await cls._max_uid()
        return str(int(max_uid) + 1) if max_uid else "100000001"

    @classmethod
    async def _ensure_user(
        cls, user_id: str, platform: str | None = None
    ) -> "UserInfo":
        """确保用户存在

        已存在时直接返回，仅在实际需要创建时才生成UID，
        避免把 ``get_new_uid`` 写进 defaults 导致每次调用都多一次排序查询。
        并发首建时依赖 user_id 唯一约束与 get_or_create 的回查路径兜底。

        参数:
            user_id: 用户ID
            platform: 平台（仅创建时写入）

        返回:
            UserInfo: 用户实例
        """
        user = await cls.filter(user_id=user_id).first()
        if user is not None:
            return user
        user, _ = await cls.get_or_create(
            user_id=user_id,
            defaults={"platform": platform, "uid": await cls._new_uid()},
        )
        return user

    @classmethod
    async def get_user(cls, user_id: str, platform: str | None = None) -> "UserInfo":
        """获取用户

        参数:
            user_id: 用户id
            platform: 平台.

        返回:
            UserInfo: UserInfo
        """
        return await cls._ensure_user(user_id, platform)

    @classmethod
    async def get_user_gold(cls, user_id: str) -> int:
        """
        获取用户金币

        参数:
            user_id: 用户ID

        返回:
            int: 用户当前金币数量
        """
        user = await cls._ensure_user(str(user_id))
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
        user = await cls._ensure_user(str(user_id))
        if not user.uid:
            new_uid = await cls._new_uid()
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
        return await cls._new_uid()

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
        """添加金币（原子操作）

        使用 ``UPDATE ... SET gold = gold + n`` 原子累加，
        避免"读取-修改-写回"在并发下丢失更新。

        参数:
            user_id: 用户id
            gold: 金币数量
            source: 插件模块
            platform: 平台.
        """
        await cls._ensure_user(user_id, platform)
        await cls.filter(user_id=str(user_id)).update(gold=cls.gold + gold)
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
        """消耗金币（原子操作）

        通过 ``WHERE gold >= n`` 条件扣减，将余额检查与扣减合并为一次
        原子 UPDATE，避免并发下两个请求同时通过余额检查导致负余额。

        参数:
            user_id: 用户id
            gold: 金币数量
            source: 插件模块
            platform: 平台.

        异常:
            InsufficientGold: 金币不足
        """
        await cls._ensure_user(user_id, platform)
        rowcount = await cls.filter(
            cls.user_id == str(user_id), cls.gold >= gold
        ).update(gold=cls.gold - gold)
        if not rowcount:
            raise InsufficientGold()
        await UserCurrLog.create_gold_log(
            user_id=user_id, gold=gold, handle=CurrHandle.PLUGIN, source=source
        )

    @classmethod
    async def set_gold(cls, user_id: str, amount: int) -> bool:
        """设置用户金币（原子覆盖）

        参数:
            user_id: 用户ID
            amount: 目标金币数量

        返回:
            bool: 用户存在且设置成功返回 True，否则 False
        """
        rowcount = await cls.filter(user_id=str(user_id)).update(gold=amount)
        return bool(rowcount)

    @classmethod
    def _run_script(cls):
        """添加items字段和uid_token并移除unique约束"""
        return [
            "ALTER TABLE user_info ADD items TEXT DEFAULT '{}';",
            "ALTER TABLE user_info ADD uid_token Text DEFAULT '';",
            "DROP INDEX IF EXISTS ix_user_info_uid_token;",
            "DROP INDEX IF EXISTS user_info_uid_token_key;",
        ]
