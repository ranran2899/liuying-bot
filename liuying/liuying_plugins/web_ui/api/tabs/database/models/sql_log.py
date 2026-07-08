from datetime import datetime
from typing import ClassVar

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class SqlLog(Model):
    """SQL执行日志模型类"""

    __tablename__ = "sql_log"
    __table_args__: ClassVar[dict] = {"comment": "sql执行日志"}

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    """自增id"""
    ip: Mapped[str] = mapped_column(String(255), comment="ip")
    """ip"""
    sql: Mapped[str] = mapped_column(Text, comment="sql")
    """sql"""
    result: Mapped[str | None] = mapped_column(Text, nullable=True, comment="结果")
    """结果"""
    is_suc: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否成功")
    """是否成功"""
    create_time: Mapped[datetime | None] = mapped_column(
        default=datetime.now, comment="创建时间"
    )
    """创建时间"""

    @classmethod
    async def add(
        cls, ip: str, sql: str, result: str | None = None, is_suc: bool = True
    ):
        """添加SQL执行日志

        参数:
            ip: ip
            sql: sql
            result: 返回结果
            is_suc: 是否成功
        """
        await cls.create(ip=ip, sql=sql, result=result, is_suc=is_suc)
