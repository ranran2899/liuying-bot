"""
Bot连接日志模型
"""

from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class BotConnectLog(Model):
    """
    Bot连接日志模型类
    
    用于记录Bot的连接和断开事件
    """
    __tablename__ = 'bot_connect_log'
    __table_args__ = {
        'comment': 'bot连接表'
    }

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment='自增id')
    """自增id"""
    bot_id: Mapped[str | None] = mapped_column(String(255), comment='Bot id')
    """Bot id"""
    platform: Mapped[str | None] = mapped_column(String(255), nullable=True, comment='平台')
    """平台"""
    connect_time: Mapped[str | None] = mapped_column(DateTime, comment='连接时间')
    """连接时间"""
    type: Mapped[int | None] = mapped_column(nullable=True, comment='1: 连接, 0: 断开')
    """1: 连接, 0: 断开"""
    create_time: Mapped[str | None] = mapped_column(DateTime, server_default=func.now(), comment='创建时间')
    """创建时间"""
