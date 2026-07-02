from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class Statistics(Model):
    """插件调用统计数据模型"""
    
    __tablename__ = "statistics"
    __table_args__ = {
        'comment': '插件调用统计数据表'
    }

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="自增ID")
    """自增id"""
    user_id: Mapped[str | None] = mapped_column(String(255), comment="用户ID")
    """用户id"""
    group_id: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="群组ID")
    """群组id"""
    plugin_name: Mapped[str | None] = mapped_column(String(255), comment="插件名称")
    """插件名称"""
    create_time: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    """添加日期"""
    bot_id: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="机器人ID")
    """Bot Id"""
    
    @classmethod
    def _run_script(cls):
        """数据库初始化脚本"""
        return [
            "ALTER TABLE statistics ADD bot_id Text DEFAULT '';",
        ]
