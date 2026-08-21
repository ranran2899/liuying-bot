"""玩家账号模型与密码学辅助。

密码使用 ``PBKDF2-HMAC-SHA256`` 加盐存储，派生计算放到线程池，避免阻塞事件循环。

账号是游戏数据的权威来源，单局战绩明细记录在 :mod:`.record` 中，二者通过
``uid`` 关联（见 :meth:`GameAccount.record_result`）。
"""

import asyncio
import hashlib
import hmac
import secrets
from datetime import datetime
from typing import Any, ClassVar, Self

from sqlalchemy import Boolean, DateTime, Float, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model

from .record import GameRecord

#: PBKDF2 迭代轮数
PBKDF2_ROUNDS = 200_000
#: 盐长度（字节）
SALT_BYTES = 16
#: 派生密钥长度（字节）
KEY_BYTES = 32
#: 用户名 / 昵称长度限制
NAME_MIN_LEN = 2
NAME_MAX_LEN = 16
#: 密码长度限制
PASSWORD_MIN_LEN = 6
PASSWORD_MAX_LEN = 64


def _derive(password: str, salt: bytes) -> bytes:
    """同步派生密钥，仅供线程池调用。

    参数:
        password: 明文密码。
        salt: 随机盐。

    返回:
        bytes: 派生出的密钥。
    """
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS, KEY_BYTES
    )


class GameAccount(Model):
    """玩家账号。

    ``best_time`` 记录最快逃脱耗时（秒，越小越好），``-1`` 表示尚无记录。
    """

    __tablename__ = "mgga_account"
    __table_args__ = ({"comment": "猛鬼公寓联机服 玩家账号表"},)

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增主键"
    )
    """自增主键"""
    uid: Mapped[int] = mapped_column(
        Integer, nullable=False, unique=True, index=True, comment="玩家唯一 ID"
    )
    """玩家唯一 ID"""
    username: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, index=True, comment="登录名"
    )
    """登录名"""
    nickname: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="游戏内昵称"
    )
    """游戏内昵称"""
    salt: Mapped[bytes] = mapped_column(
        LargeBinary(SALT_BYTES), nullable=False, comment="密码盐"
    )
    """密码盐"""
    pwd_hash: Mapped[bytes] = mapped_column(
        LargeBinary(KEY_BYTES), nullable=False, comment="密码派生值"
    )
    """密码派生值"""
    escapes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="逃脱次数"
    )
    """逃脱次数"""
    deaths: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="死亡次数"
    )
    """死亡次数"""
    best_time: Mapped[float] = mapped_column(
        Float, nullable=False, default=-1.0, comment="最快逃脱耗时（秒），-1 为无记录"
    )
    """最快逃脱耗时（秒），-1 为无记录"""
    total_time: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="累计游戏时长（秒）"
    )
    """累计游戏时长（秒）"""
    banned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否封禁"
    )
    """是否封禁"""
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="注册时间"
    )
    """注册时间"""
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="最近登录时间"
    )
    """最近登录时间"""

    #: 同一用户名的注册/登录串行化，避免并发下重复建号
    _locks: ClassVar[dict[str, asyncio.Lock]] = {}

    @classmethod
    def _lock_of(cls, username: str) -> asyncio.Lock:
        """获取指定用户名的互斥锁。

        参数:
            username: 登录名。

        返回:
            asyncio.Lock: 该用户名对应的锁。
        """
        lock = cls._locks.get(username)
        if lock is None:
            lock = cls._locks[username] = asyncio.Lock()
        return lock

    @classmethod
    async def register(cls, username: str, password: str, nickname: str) -> Self | None:
        """注册新账号。

        参数:
            username: 登录名。
            password: 明文密码。
            nickname: 游戏内昵称。

        返回:
            Self | None: 新账号，用户名已存在时返回 ``None``。
        """
        async with cls._lock_of(username):
            if await cls.filter(username=username).exists():
                return None
            salt = secrets.token_bytes(SALT_BYTES)
            pwd_hash = await asyncio.to_thread(_derive, password, salt)
            return await cls.create(
                username=username,
                nickname=nickname,
                salt=salt,
                pwd_hash=pwd_hash,
                last_login=datetime.now(),
            )

    @classmethod
    async def verify(cls, username: str, password: str) -> Self | None:
        """校验用户名与密码。

        参数:
            username: 登录名。
            password: 明文密码。

        返回:
            Self | None: 校验通过的账号，否则 ``None``。
        """
        account = await cls.filter(username=username).first()
        if account is None:
            # 用户不存在时同样做一次派生，抹平响应时间差以防用户名枚举
            await asyncio.to_thread(_derive, password, b"\x00" * SALT_BYTES)
            return None
        pwd_hash = await asyncio.to_thread(_derive, password, account.salt)
        if not hmac.compare_digest(pwd_hash, account.pwd_hash):
            return None
        return account

    async def touch_login(self) -> None:
        """刷新最近登录时间。"""
        self.last_login = datetime.now()
        await self.save()

    async def rename(self, nickname: str) -> None:
        """修改游戏内昵称。

        参数:
            nickname: 新昵称。
        """
        self.nickname = nickname
        await self.save()

    @classmethod
    async def record_result(
        cls, uid: int, escaped: bool, survive: float, seed: int = 0
    ) -> Self | None:
        """写入一局战绩并累加账号统计。

        参数:
            uid: 玩家 ID。
            escaped: 是否成功逃脱。
            survive: 本局存活/逃脱耗时（秒）。
            seed: 关卡随机种子，便于复盘。

        返回:
            Self | None: 更新后的账号，不存在时返回 ``None``。
        """
        account = await cls.filter(uid=uid).first()
        if account is None:
            return None

        account.total_time += survive
        if escaped:
            account.escapes += 1
            if account.best_time < 0 or survive < account.best_time:
                account.best_time = survive
        else:
            account.deaths += 1
        await account.save()

        await GameRecord.create(
            uid=uid, escaped=escaped, survive_time=survive, seed=seed
        )
        return account

    def profile(self) -> dict[str, Any]:
        """返回下发给客户端的档案数据。

        返回:
            dict[str, Any]: 档案字段。
        """
        total = self.escapes + self.deaths
        return {
            "uid": self.uid,
            "username": self.username,
            "nickname": self.nickname,
            "escapes": self.escapes,
            "deaths": self.deaths,
            "total": total,
            "rate": round(self.escapes / total * 100, 1) if total else 0.0,
            "best_time": round(self.best_time, 2) if self.best_time >= 0 else None,
            "total_time": round(self.total_time, 1),
        }

    @classmethod
    def _run_script(cls) -> list[str]:
        """数据库迁移脚本sql。

        
        """
        return [
            # "DROP TABLE IF EXISTS mgga_account;",
        ]


    @classmethod
    async def leaderboard(cls, limit: int = 10) -> list[Self]:
        """按逃脱次数取排行榜。

        参数:
            limit: 返回条数。

        返回:
            list[Self]: 账号列表。
        """
        return await cls.filter().order_by("-escapes", "best_time").limit(limit).all()
