"""用户签到日志模型"""

from datetime import datetime

from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class UserSignLog(Model):
    """用户签到日志模型
    
    用于记录用户每日签到记录，支持按年月统计签到次数
    """

    __tablename__ = "user_sign_log"
    __table_args__ = {"comment": "用户签到日志表，用于记录用户每日签到记录"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="自增id")
    """自增id"""
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True, comment="用户id")
    """用户id"""
    sign_date: Mapped[datetime] = mapped_column(nullable=False, comment="签到日期")
    """签到日期"""
    year: Mapped[int] = mapped_column(nullable=False, comment="年份")
    """年份"""
    month: Mapped[int] = mapped_column(nullable=False, comment="月份")
    """月份"""
    create_time: Mapped[datetime] = mapped_column(default=datetime.now, comment="创建时间")
    """创建时间"""

    @classmethod
    async def add_sign_log(cls, user_id: str, sign_date: datetime) -> bool:
        """
        添加签到记录
        
        参数:
            user_id: 用户ID
            sign_date: 签到日期
            
        返回:
            bool: 添加成功返回True，失败返回False
        """
        await cls.create(
            user_id=user_id,
            sign_date=sign_date,
            year=sign_date.year,
            month=sign_date.month,
            db_name="log_db",
        )
        return True

    @classmethod
    async def get_month_sign_count(cls, user_id: str, year: int, month: int) -> int:
        """
        获取用户某年某月的签到次数
        
        参数:
            user_id: 用户ID
            year: 年份
            month: 月份
            
        返回:
            int: 该月的签到次数
        """
        return await cls.filter(user_id=user_id, year=year, month=month).using("log_db").count()

    @classmethod
    async def get_year_sign_count(cls, user_id: str, year: int) -> int:
        """
        获取用户某年的签到次数
        
        参数:
            user_id: 用户ID
            year: 年份
            
        返回:
            int: 该年的签到次数
        """
        return await cls.filter(user_id=user_id, year=year).using("log_db").count()

    @classmethod
    async def get_month_sign_dates(cls, user_id: str, year: int, month: int) -> list[datetime]:
        """
        获取用户某年某月的所有签到日期
        
        参数:
            user_id: 用户ID
            year: 年份
            month: 月份
            
        返回:
            list[datetime]: 该月的所有签到日期列表
        """
        logs = await cls.filter(user_id=user_id, year=year, month=month).using("log_db").all()
        return [log.sign_date for log in logs]

    @classmethod
    async def get_year_sign_dates(cls, user_id: str, year: int) -> list[datetime]:
        """
        获取用户某年的所有签到日期
        
        参数:
            user_id: 用户ID
            year: 年份
            
        返回:
            list[datetime]: 该年的所有签到日期列表
        """
        logs = await cls.filter(user_id=user_id, year=year).using("log_db").all()
        return [log.sign_date for log in logs]

    @classmethod
    async def check_sign_by_date(cls, user_id: str, sign_date: datetime) -> bool:
        """
        检查用户在指定日期是否签到
        
        参数:
            user_id: 用户ID
            sign_date: 签到日期
            
        返回:
            bool: 已签到返回True，未签到返回False
        """
        log = await cls.filter(
            user_id=user_id,
            year=sign_date.year,
            month=sign_date.month,
            sign_date=sign_date,
        ).using("log_db").first()
        return log is not None

    @classmethod
    async def get_all_sign_dates(cls, user_id: str) -> list[datetime]:
        """
        获取用户的所有签到日期
        
        参数:
            user_id: 用户ID
            
        返回:
            list[datetime]: 用户的所有签到日期列表
        """
        logs = await cls.filter(user_id=user_id).using("log_db").all()
        return [log.sign_date for log in logs]

    @classmethod
    async def get_total_sign_count(cls, user_id: str) -> int:
        """
        获取用户的总签到次数
        
        参数:
            user_id: 用户ID
            
        返回:
            int: 用户的总签到次数
        """
        return await cls.filter(user_id=user_id).using("log_db").count()

    @classmethod
    async def get_recent_six_months_data(cls, user_id: str) -> dict:
        """
        获取用户最近6个月的签到统计数据
        
        参数:
            user_id: 用户ID
            
        返回:
            dict: 包含月份标签和签到次数的字典
        """
        now = datetime.now()
        months = []
        counts = []

        for i in range(5, -1, -1):
            target_year = now.year
            target_month = now.month - i

            if target_month <= 0:
                target_month += 12
                target_year -= 1

            month_label = f"{target_month}月"
            count = await cls.get_month_sign_count(user_id, target_year, target_month)
            months.append(month_label)
            counts.append(count)

        return {"months": months, "counts": counts}
