from datetime import datetime

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model
from liuying.utils.enum import EventLogType


class EventLog(Model):
    """事件日志模型类
    
    用于记录各种事件通知
    """
    __tablename__ = 'event_log'
    __table_args__ = {
        'comment': '各种请求通知记录表'
    }
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment='自增id')
    """自增id"""
    user_id: Mapped[str | None] = mapped_column(String(255), comment='用户id')
    """用户id"""
    group_id: Mapped[str | None] = mapped_column(String(255), comment='群组id')
    """群组id"""
    event_type: Mapped[EventLogType | None] = mapped_column(Enum(EventLogType), default=None, comment='类型')
    """类型"""
    create_time: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now, comment='创建时间')
    """创建时间"""
