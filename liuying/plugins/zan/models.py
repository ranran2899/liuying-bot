from datetime import datetime
from typing import List

from sqlalchemy import String, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class ZanSubscribe(Model):
    """
    点赞订阅模型类

    用于存储和管理点赞订阅用户，支持多机器人标记
    """
    __tablename__ = 'zan_subscribe'
    __table_args__ = (
        UniqueConstraint('user_id', 'bot_id', name='uq_user_bot'),
        {
            'comment': '点赞订阅表，用于存储和管理点赞订阅用户'
        },
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment='自增id')
    """自增id"""
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True, comment='用户ID')
    """用户ID"""
    bot_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True, comment='订阅机器人ID')
    """订阅机器人ID"""
    create_time: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now, comment='订阅时间')
    """订阅时间"""

    @classmethod
    async def get_all_subscribers(cls) -> List[str]:
        """
        获取所有订阅用户ID（去重）

        返回:
            List[str]: 订阅用户ID列表
        """
        subscribers = await cls.filter().all()
        return list({sub.user_id for sub in subscribers})

    @classmethod
    async def get_subscribers_by_bot(cls, bot_id: str) -> List[str]:
        """
        获取指定机器人的订阅用户ID列表

        参数:
            bot_id: 机器人ID

        返回:
            List[str]: 订阅用户ID列表
        """
        subscribers = await cls.filter(bot_id=bot_id).all()
        return [sub.user_id for sub in subscribers]

    @classmethod
    async def is_subscribed(cls, user_id: str, bot_id: str) -> bool:
        """
        检查用户是否已在指定机器人下订阅

        参数:
            user_id: 用户ID
            bot_id: 机器人ID

        返回:
            bool: 是否已订阅
        """
        return await cls.filter(user_id=str(user_id), bot_id=bot_id).exists()

    @classmethod
    async def add_subscriber(cls, user_id: str, bot_id: str) -> bool:
        """
        添加订阅用户

        参数:
            user_id: 用户ID
            bot_id: 机器人ID

        返回:
            bool: 是否添加成功
        """
        try:
            if await cls.is_subscribed(user_id, bot_id):
                return False
            await cls.create(user_id=str(user_id), bot_id=bot_id)
            return True
        except Exception:
            return False

    @classmethod
    async def remove_subscriber(cls, user_id: str, bot_id: str) -> bool:
        """
        移除指定机器人下的订阅用户

        参数:
            user_id: 用户ID
            bot_id: 机器人ID

        返回:
            bool: 是否移除成功
        """
        try:
            subscriber = await cls.filter(user_id=str(user_id), bot_id=bot_id).first()
            if subscriber:
                await subscriber.delete()
                return True
            return False
        except Exception:
            return False

    @classmethod
    async def get_subscriber_count(cls) -> int:
        """
        获取订阅用户数量（去重）

        返回:
            int: 订阅用户数量
        """
        subscribers = await cls.filter().all()
        return len({sub.user_id for sub in subscribers})
