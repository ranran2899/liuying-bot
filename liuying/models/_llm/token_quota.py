"""用户 Token 额度模型"""
from datetime import datetime
from typing import ClassVar

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.models._user.user_curr import UserCurr
from liuying.services.liuying_db import Model
from liuying.utils.exception import InsufficientCopper


class UserToken(Model):
    """用户 Token 额度模型

    按用户维度存储 token 额度。
    """

    __tablename__ = "llm_user_token"
    __table_args__: ClassVar[dict] = {
        "comment": "用户 Token 额度表"
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    """自增id"""
    user_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True,
        comment="用户id"
    )
    """用户id"""
    user_token: Mapped[int] = mapped_column(
        BigInteger, default=10000, comment="token 额度"
    )
    """token 额度"""
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.now, comment="最后更新时间"
    )
    """最后更新时间"""


    @classmethod
    async def consume(
        cls, user_id: str, tokens: int
    ) -> "UserToken":
        """消耗用户 token 额度

        用户无记录时自动创建（user_token=0），token 额度不足时
        自动以铜币抵扣（1 铜币 = 1 token），铜币也不足时抛出
        InsufficientCopper。

        参数:
            user_id: 用户id
            tokens: 消耗的 token 数

        返回:
            UserToken: 更新后的 token 记录

        异常:
            InsufficientCopper: token 与铜币均不足
        """
        if tokens <= 0:
            instance, _ = await cls.get_or_create(
                user_id=user_id,
                # defaults={"updated_at": datetime.now()},
            )
            return instance

        instance, _ = await cls.get_or_create(
            user_id=user_id,
            # defaults={"updated_at": datetime.now()},
        )
        now = datetime.now()

        if instance.user_token >= tokens:
            instance.user_token -= tokens
            instance.updated_at = now
            await instance.save(
                update_fields=["user_token", "updated_at"]
            )
            return instance

        # token 不足，使用铜币抵扣剩余部分
        need_copper = tokens - instance.user_token
        user_curr, _ = await UserCurr.get_or_create(user_id=user_id)
        if user_curr.copper < need_copper:
            raise InsufficientCopper()

        user_curr.copper -= need_copper
        await user_curr.save(update_fields=["copper"])

        instance.user_token = 0
        instance.updated_at = now
        await instance.save(
            update_fields=["user_token", "updated_at"]
        )
        return instance

    @classmethod
    async def get_available(cls, user_id: str) -> int:
        """获取用户可用 token 总额度

        参数:
            user_id: 用户id

        返回:
            int: 可用 token 总额 = user_token + copper
        """
        instance, _ = await cls.get_or_create(user_id=user_id)
        user_token = instance.user_token if instance else 0
        user_curr, _ = await UserCurr.get_or_create(user_id=user_id)
        return user_token + user_curr.copper

    @classmethod
    async def set_token(cls, user_id: str, tokens: int) -> "UserToken":
        """设置用户 token 额度

        参数:
            user_id: 用户id
            tokens: token 额度

        返回:
            UserToken: 更新后的记录
        """
        instance = await cls.filter(user_id=user_id).first()
        if instance is None:
            instance = cls(user_id=user_id)
        instance.user_token = tokens
        instance.updated_at = datetime.now()
        await instance.save(update_fields=["user_token", "updated_at"])
        return instance

    @classmethod
    async def reset_all(cls, tokens: int) -> int:
        """批量重置所有用户 token 额度

        将所有用户的 token 额度统一重置为指定值，并更新最后更新时间。

        参数:
            tokens: 重置后的 token 额度

        返回:
            int: 受影响的用户记录数
        """
        now = datetime.now()
        updated_count = await cls.filter().update(
            user_token=tokens,
            updated_at=now,
        )
        return updated_count

    @classmethod
    def _run_script(cls):
        """数据库初始化脚本"""
        return [
            # "DROP TABLE IF EXISTS llm_user_token;",
        ]

# 保留向后兼容接口
async def get_user_token(user_id: str) -> int:
    """查看用户可用 token 额度

    返回 user_token + copper 总额

    参数:
        user_id: 用户id

    返回:
        int: 可用 token 额度
    """
    return await UserToken.get_available(user_id)


