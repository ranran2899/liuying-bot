"""用户签到模型"""

from datetime import datetime, timedelta

from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model
from .user_sign_log import UserSignLog


class UserSignInfo(Model):
    """用户签到模型"""

    __tablename__ = "user_sign"
    __table_args__ = {"comment": "用户签到表，用于管理用户签到信息"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="自增id")
    """自增id"""
    user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, comment="用户id")
    """用户id"""
    is_signed_in: Mapped[int] = mapped_column(default=0, comment="是否签到，判断：0为未签到，1为已签到")
    """签到状态"""
    total_days: Mapped[int] = mapped_column(default=0, comment="累计签到天数")
    """累计签到天数"""
    consecutive_days: Mapped[int] = mapped_column(default=0, comment="连续签到天数")
    """连续签到天数"""
    sign_in_date: Mapped[datetime | None] = mapped_column(nullable=True, comment="签到日期")
    """签到日期"""
    last_sign_in_date: Mapped[datetime | None] = mapped_column(nullable=True, comment="上一次签到日期")
    """上一次签到日期"""
    first_sign_in_date: Mapped[datetime | None] = mapped_column(nullable=True, comment="首次签到日期")
    """首次签到日期"""
    platform: Mapped[str] = mapped_column(String(255), default="", comment="签到平台")
    """签到平台"""

    @classmethod
    async def check_user_sign_status(cls, user_id: str) -> int:
        """
        检查用户是否已签到

        参数:
            user_id: 用户ID

        返回:
            int: 0表示未签到，1表示已签到
        """
        user = await cls.safe_get_or_none(user_id=user_id)
        if user and user.is_signed_in == 1:
            return 1
        return 0

    @classmethod
    async def get_all_signed_in_users(cls):
        """
        获取所有已签到的用户列表

        返回:
            list: 所有已签到(is_signed_in=1)的用户列表
        """
        return await cls.filter(is_signed_in=1).all()

    @classmethod
    async def reset_all_signed_in_users(cls) -> int:
        """
        重置所有已签到用户的状态为未签到

        返回:
            int: 重置的用户数量
        """
        result = await cls.filter(is_signed_in=1).update(is_signed_in=0)
        return result

    @classmethod
    async def sign(cls, user_id: str) -> bool:
        """
        签到
        
        基于自然日(晚上24:00)作为连续签到状态的重置时间节点。
        跨午夜签到场景：在23:59签到后，于00:01再次签到判定为连续签到。

        参数:
            user_id: 用户ID

        返回:
            bool: 更新成功返回True，失败返回False
        """
        try:
            now = datetime.now()
            today = now.date()
            yesterday = today - timedelta(days=1)

            user, _ = await cls.update_or_create(user_id=user_id, defaults={})

            if user.first_sign_in_date is None:
                user.first_sign_in_date = now

            last_sign_date = user.sign_in_date.date() if user.sign_in_date else None
            
            if last_sign_date == yesterday:
                user.consecutive_days += 1
            elif last_sign_date == today:
                pass
            else:
                user.consecutive_days = 1

            user.is_signed_in = 1
            user.total_days += 1
            user.last_sign_in_date = user.sign_in_date
            user.sign_in_date = now
            await user.save()

            await UserSignLog.add_sign_log(user_id=user_id, sign_date=now)

            return True
        except Exception as e:
            from liuying.utils.log import logger
            logger.error(f"用户 {user_id} 签到失败: {e}")
            return False

    @classmethod
    async def set_user_sign_status(cls, user_id: str, status: int) -> bool:
        """
        设置用户签到状态

        参数:
            user_id: 用户ID
            status: 签到状态，0表示未签到，1表示已签到

        返回:
            bool: 设置成功返回True，失败返回False
        """
        user, _ = await cls.get_or_create(user_id=user_id)
        user.is_signed_in = status
        await user.save()
        return True

    @classmethod
    async def set_total_days(cls, user_id: str, days: int) -> bool:
        """
        设置用户累计签到天数

        参数:
            user_id: 用户ID
            days: 要设置的累计签到天数，必须为非负数

        返回:
            bool: 设置成功返回True，失败返回False
        """
        if days < 0:
            return False

        user, _ = await cls.get_or_create(user_id=user_id)
        user.total_days = days
        await user.save()
        return True

    @classmethod
    async def set_consecutive_days(cls, user_id: str, days: int) -> bool:
        """
        设置用户连续签到天数

        参数:
            user_id: 用户ID
            days: 要设置的连续签到天数，必须为非负数

        返回:
            bool: 设成功返回True，失败返回False
        """
        if days < 0:
            return False

        user, _ = await cls.get_or_create(user_id=user_id)
        user.consecutive_days = days
        await user.save()
        return True

    @classmethod
    async def get_total_days(cls, user_id: str) -> int:
        """
        获取用户累计签到天数

        参数:
            user_id: 用户ID

        返回:
            int: 用户的累计签到天数，如果用户不存在则返回0
        """
        user = await cls.safe_get_or_none(user_id=user_id)
        return user.total_days if user else 0

    @classmethod
    async def get_consecutive_days(cls, user_id: str) -> int:
        """
        获取用户连续签到天数

        参数:
            user_id: 用户ID

        返回:
            int: 用户的连续签到天数，如果用户不存在则返回0
        """
        user = await cls.safe_get_or_none(user_id=user_id)
        return user.consecutive_days if user else 0

    @classmethod
    async def get_sign_in_date(cls, user_id: str) -> datetime | None:
        """
        获取用户签到日期

        参数:
            user_id: 用户ID

        返回:
            datetime | None: 用户的签到日期，如果用户不存在或未签到则返回None
        """
        user = await cls.safe_get_or_none(user_id=user_id)
        return user.sign_in_date if user else None

    @classmethod
    async def get_last_sign_in_date(cls, user_id: str) -> datetime | None:
        """
        获取用户上一次签到日期

        参数:
            user_id: 用户ID

        返回:
            datetime | None: 用户的上一次签到日期，如果用户不存在或没有上一次签到记录则返回None
        """
        user = await cls.safe_get_or_none(user_id=user_id)
        return user.last_sign_in_date if user else None

    @classmethod
    async def set_sign_in_date(cls, user_id: str, date: datetime) -> bool:
        """
        设置用户签到日期

        参数:
            user_id: 用户ID
            date: 要设置的签到日期

        返回:
            bool: 设置成功返回True，失败返回False
        """
        user, _ = await cls.get_or_create(user_id=user_id)
        user.sign_in_date = date
        await user.save()
        return True

    @classmethod
    async def set_last_sign_in_date(cls, user_id: str, date: datetime) -> bool:
        """
        设置用户上一次签到日期

        参数:
            user_id: 用户ID
            date: 要设置的上一次签到日期

        返回:
            bool: 设置成功返回True，失败返回False
        """
        user, _ = await cls.get_or_create(user_id=user_id)
        user.last_sign_in_date = date
        await user.save()
        return True

    @classmethod
    async def get_first_sign_in_date(cls, user_id: str) -> datetime | None:
        """
        获取用户首次签到日期

        参数:
            user_id: 用户ID

        返回:
            datetime | None: 用户的首次签到日期，如果用户不存在则返回None
        """
        user = await cls.safe_get_or_none(user_id=user_id)
        return user.first_sign_in_date if user else None

    @classmethod
    async def set_first_sign_in_date(cls, user_id: str, date: datetime) -> bool:
        """
        设置用户首次签到日期

        参数:
            user_id: 用户ID
            date: 要设置的首次签到日期

        返回:
            bool: 设置成功返回True，失败返回False
        """
        user, _ = await cls.get_or_create(user_id=user_id)
        user.first_sign_in_date = date
        await user.save()
        return True

    @classmethod
    async def _run_script(cls):
        """
        数据库迁移脚本
        """
        return ["ALTER TABLE user_sign ADD first_sign_in_date DATETIME NULL;"]
