"""被动技能信息表"""

from typing import ClassVar

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class TaskInfo(Model):
    """被动技能信息模型"""

    __tablename__ = "task_info"
    __table_args__: ClassVar[dict[str, str]] = {"comment": "任务基本信息表"}

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    """自增id"""
    module: Mapped[str | None] = mapped_column(
        String(255), comment="被动技能模块名"
    )
    """被动技能模块名"""
    name: Mapped[str | None] = mapped_column(
        String(255), comment="被动技能名称"
    )
    """被动技能名称"""
    status: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="全局开关状态"
    )
    """全局开关状态"""
    load_status: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="加载状态"
    )
    """加载状态"""
    default_status: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="进群默认开关状态"
    )
    """进群默认开关状态"""
    run_time: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="运行时间"
    )
    """运行时间"""
    run_count: Mapped[int] = mapped_column(default=0, comment="运行次数")
    """运行次数"""

    @classmethod
    async def sync_load_status(cls, loaded_modules: list[str]) -> None:
        """同步被动技能加载状态

        参数:
            loaded_modules: 已加载的被动技能模块名列表
        """
        if loaded_modules:
            await cls.filter(cls.module.in_(loaded_modules)).update(load_status=True)
            await cls.filter(~cls.module.in_(loaded_modules)).update(
                load_status=False
            )
        else:
            await cls.filter().update(load_status=False)
