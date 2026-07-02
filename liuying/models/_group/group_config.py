from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class GroupConfig(Model):
    __tablename__ = 'group_config'
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    """自增id"""
    group_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    """群号"""
    auto_reply: Mapped[bool] = mapped_column(Boolean, default=True)
    """自动回复开关"""
    repeat: Mapped[bool] = mapped_column(Boolean, default=True)
    """复读开关"""
    repeat_probability: Mapped[int] = mapped_column(default=30)
    """复读概率"""
    welcome: Mapped[bool] = mapped_column(Boolean, default=True)
    """欢迎新人开关"""
    welcome_msg: Mapped[str] = mapped_column(Text, default="欢迎新人～")
    """欢迎消息"""
    create_time: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)
    """创建时间"""
    update_time: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    """更新时间"""
    
    def __init__(self, group_id: str):
        """
        初始化群配置
        
        参数:
            group_id: 群号
        """
        self.group_id = group_id

