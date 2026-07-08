"""聊天历史记录模型"""

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class ChatHistory(Model):
    """聊天历史记录模型类

    用于记录机器人接收到的消息历史
    """

    __tablename__ = "chat_history"
    __table_args__ = {"comment": "聊天历史记录表"}

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    """自增id"""
    user_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="用户id"
    )
    """用户id"""
    group_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="群组id"
    )
    """群组id"""
    bot_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Bot ID"
    )
    """Bot ID"""
    message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="消息内容")
    """消息内容"""
    create_time: Mapped[datetime | None] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间"
    )
    """创建时间"""
