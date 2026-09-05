"""用户签到模型"""

from datetime import datetime, timedelta
from typing import ClassVar

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model

from .user_sign_log import UserSignLog


class UserSignInfo(Model):
    """用户签到模型"""

    __tablename__ = "user_sign"
    __table_args__: ClassVar[dict[str, str]] = {
        "comment": "用户签到表，用于管理用户签到信息"
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    """自增id"""
    user_id: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, comment="用户id"
    )
    """用户id"""
    is_signed_in: Mapped[int] = mapped_column(
        default=0, comment="是否签到，判断：0为未签到，1为已签到"
    )
    """签到状态"""
    total_days: Mapped[int] = mapped_column(default=0, comment="累计签到天数")
    """累计签到天数"""
    consecutive_days: Mapped[int] = mapped_column(default=0, comment="连续签到天数")
    """连续签到天数"""
    sign_in_date: Mapped[datetime | None] = mapped_column(
        nullable=True, comment="签到日期"
    )
    """签到日期"""
    last_sign_in_date: Mapped[datetime | None] = mapped_column(
        nullable=True, comment="上一次签到日期"
    )
    """上一次签到日期"""
    first_sign_in_date: Mapped[datetime | None] = mapped_column(
        nullable=True, comment="首次签到日期"
    )
    """首次签到日期"""
    platform: Mapped[str] = mapped_column(String(255), default="", comment="签到平台")
    """签到平台"""

    @classmethod
    async def sign(cls, user_id: str) -> "UserSignInfo":
        """执行签到并返回更新后的签到记录

        基于自然日(24:00)作为连续签到的重置节点，跨午夜签到(23:59签到后00:01再签)判定为连续签到。

        参数:
            user_id: 用户ID

        返回:
            UserSignInfo: 更新后的签到记录
        """
        now = datetime.now()
        today = now.date()
        yesterday = today - timedelta(days=1)

        user, _ = await cls.update_or_create(user_id=user_id)

        if user.first_sign_in_date is None:
            user.first_sign_in_date = now

        last_sign_date = user.sign_in_date.date() if user.sign_in_date else None
        if last_sign_date == yesterday:
            user.consecutive_days += 1
        elif last_sign_date != today:
            user.consecutive_days = 1

        user.is_signed_in = 1
        user.total_days += 1
        user.last_sign_in_date = user.sign_in_date
        user.sign_in_date = now
        await user.save()

        await UserSignLog.add_sign_log(user_id=user_id, sign_date=now)
        return user

    @classmethod
    async def reset_all_signed_in_users(cls) -> int:
        """重置所有已签到用户的状态为未签到

        返回:
            int: 重置的用户数量
        """
        return await cls.filter(is_signed_in=1).update(is_signed_in=0)

    @classmethod
    async def _run_script(cls) -> list[str]:
        """数据库迁移脚本"""
        return ["ALTER TABLE user_sign ADD first_sign_in_date DATETIME NULL;"]
