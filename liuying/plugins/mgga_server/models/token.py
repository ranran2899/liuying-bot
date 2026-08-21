"""免密登录令牌模型。

令牌由 :meth:`GameToken.issue` 签发，与 :class:`~.account.GameAccount` 通过
``uid`` 关联。一次只保留玩家的最新令牌，签发即吊销旧令牌。
"""

import secrets
from datetime import datetime, timedelta

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model
from liuying.utils.log import logger

from .account import GameAccount


class GameToken(Model):
    """免密登录令牌。"""

    __tablename__ = "mgga_token"
    __table_args__ = ({"comment": "猛鬼公寓联机服 登录令牌表"},)

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增主键"
    )
    """自增主键"""
    token: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True, comment="令牌"
    )
    """令牌"""
    uid: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True, comment="所属玩家 ID"
    )
    """所属玩家 ID"""
    expires_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True, comment="过期时间"
    )
    """过期时间"""

    @classmethod
    async def issue(cls, uid: int, ttl_days: int) -> str:
        """签发新令牌，并顺手清掉该玩家的历史令牌。

        参数:
            uid: 玩家 ID。
            ttl_days: 有效天数。

        返回:
            str: 新令牌。
        """
        await cls.filter(uid=uid).delete()
        token = secrets.token_urlsafe(32)
        await cls.create(
            token=token,
            uid=uid,
            expires_at=datetime.now() + timedelta(days=ttl_days),
        )
        return token

    @classmethod
    async def resolve(cls, token: str) -> GameAccount | None:
        """用令牌换取账号。

        参数:
            token: 令牌。

        返回:
            GameAccount | None: 有效令牌对应的账号，否则 ``None``。
        """
        row = await cls.filter(token=token).first()
        if row is None:
            return None
        if row.expires_at <= datetime.now():
            await row.delete()
            return None
        return await GameAccount.filter(uid=row.uid).first()

    @classmethod
    async def revoke(cls, uid: int) -> None:
        """吊销某玩家的全部令牌。

        参数:
            uid: 玩家 ID。
        """
        await cls.filter(uid=uid).delete()

    @classmethod
    def _run_script(cls) -> list[str]:
        """数据库迁移脚本。

        旧版 ``mgga_token`` 表可能缺 ``token / uid / expires_at`` 三列。
        这里用 ``ALTER TABLE ADD ... DEFAULT ...`` 幂等补齐，列已存在时
        由框架忽略 ``duplicate column`` 异常。
        """
        return [
           # "DROP TABLE IF EXISTS mgga_token;",
        ]


    @classmethod
    async def purge_expired(cls) -> int:
        """清理过期令牌。

        返回:
            int: 清理条数。
        """
        removed = await cls.filter(expires_at__lt=datetime.now()).delete()
        if removed:
            logger.debug(f"[mgga_server] 清理过期令牌 {removed} 条")
        return removed
