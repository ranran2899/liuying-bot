"""机器人信息"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db.base_model import Model


class BotInfo(Model):
    """机器人信息数据模型"""
    __tablename__ = "bot_info"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="自增id")
    """自增id"""
    bot_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, comment="bot_id")
    """bot_id"""
    bot_name: Mapped[str | None] = mapped_column(String(255), default="", comment="机器人名称")
    """机器人名称"""
    bot_avatar: Mapped[str | None] = mapped_column(String(255), default="", comment="机器人头像")
    """机器人头像"""
    bot_other_id: Mapped[str | None] = mapped_column(String(255), default="", comment="机器人其他id")
    """机器人其他id，用于唯一标识机器人（如果有）"""
    # bot_cache = CacheType.BOT
    # """机器人缓存类型"""
    # bot_cache_data =
    # """机器人缓存数据"""
