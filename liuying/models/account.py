"""
账号密码模型
"""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class AccountPassword(Model):
    """
    账号密码模型类
    
    用于管理系统中的账号密码信息
    """
    
    __tablename__ = "account_password"
    __table_args__ = {"comment": "账号密码表，用于管理系统中的账号密码信息"}
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="自增id")
    """自增id"""
    account: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, comment="账号")
    """账号"""
    password: Mapped[str] = mapped_column(String(255), nullable=False, comment="密码")
    """密码"""
    status: Mapped[int] = mapped_column(default=0, comment="账号状态：0-不存在 1-正常 2-禁用 3-冻结")
    """账号状态：0-不存在 1-正常 2-禁用 3-冻结"""
    platform: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="所在平台")
    """所在平台"""
    description: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="账号描述")
    """账号描述"""
    create_time: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    """创建时间"""
    
    @classmethod
    async def exists(cls, account: str) -> bool:
        """
        检查账号是否存在
        
        参数:
            account: 要检查的账号名
            
        返回:
            bool: 账号是否存在
        """
        instance = await cls.safe_get_or_none(account=account)
        return instance is not None
    
    @classmethod
    async def get_status(cls, account: str) -> int:
        """
        查询账号状态
        
        参数:
            account: 要查询的账号名
            
        返回:
            int: 账号状态码
                0-不存在
                1-正常
                2-禁用
                3-冻结
        """
        result = await cls.filter(account=account).first()
        return result.status if result else 0
