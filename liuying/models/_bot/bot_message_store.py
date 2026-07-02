from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db.base_model import Model
from liuying.utils.enum import BotSentType


class BotMessageStore(Model):
    """Bot发送消息数据模型"""

    __tablename__ = "bot_message_store"
    __table_args__ = {"comment": "Bot发送消息列表"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="自增id")
    """自增id"""
    bot_id: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="bot id")
    """bot id"""
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="目标id")
    """目标id"""
    group_id: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="群组id")
    """群组id"""
    sent_type: Mapped[str] = mapped_column(String(50), nullable=False, default=BotSentType, comment="类型")
    """类型"""
    text: Mapped[str | None] = mapped_column(Text, nullable=True, comment="文本内容")
    """文本内容"""
    plain_text: Mapped[str | None] = mapped_column(Text, nullable=True, comment="纯文本")
    """纯文本"""
    platform: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="平台")
    """平台"""
    create_time: Mapped[str | None] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    """创建时间"""
