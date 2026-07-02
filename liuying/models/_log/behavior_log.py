from typing import ClassVar

from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class BehaviorLog(Model):
    """用户行为日志模型类

    用于记录用户命令调用行为
    """

    __tablename__ = "behavior_log"
    __table_args__: ClassVar[dict] = {
        "comment": "用户行为日志表，记录命令调用行为"
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    """自增id"""
    user_id: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="用户id"
    )
    """用户id"""
    group_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="群组id"
    )
    """群组id"""
    channel_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="频道id"
    )
    """频道id"""
    module: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="插件模块名"
    )
    """插件模块名"""
    command: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="命令内容"
    )
    """命令内容"""
    raw_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="原始消息"
    )
    """原始消息"""
    status: Mapped[int] = mapped_column(
        Integer, default=0, comment="执行状态 0-成功 1-失败 2-忽略"
    )
    """执行状态"""
    error_msg: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="错误信息"
    )
    """错误信息"""
    platform: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="平台"
    )
    """平台"""
    bot_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Bot ID"
    )
    """Bot ID"""
    create_time: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="创建时间戳"
    )
    """创建时间戳"""

    @classmethod
    async def add_log(
        cls,
        user_id: str,
        module: str,
        group_id: str | None = None,
        channel_id: str | None = None,
        command: str | None = None,
        raw_message: str | None = None,
        status: int = 0,
        error_msg: str | None = None,
        platform: str | None = None,
        bot_id: str | None = None,
    ) -> "BehaviorLog":
        """添加行为日志

        参数:
            user_id: 用户id
            module: 模块名
            group_id: 群组id
            channel_id: 频道id
            command: 命令内容
            raw_message: 原始消息
            status: 状态
            error_msg: 错误信息
            platform: 平台
            bot_id: Bot ID

        返回:
            BehaviorLog: 日志对象
        """
        import time

        return await cls.create(
            user_id=user_id,
            group_id=group_id,
            channel_id=channel_id,
            module=module,
            command=command[:500] if command else None,
            raw_message=raw_message[:5000] if raw_message else None,
            status=status,
            error_msg=error_msg[:500] if error_msg else None,
            platform=platform,
            bot_id=bot_id,
            create_time=int(time.time()),
        )

    @classmethod
    async def get_user_logs(
        cls, user_id: str, limit: int = 100
    ) -> list["BehaviorLog"]:
        """获取用户日志

        参数:
            user_id: 用户id
            limit: 返回数量限制

        返回:
            list[BehaviorLog]: 日志列表
        """
        return (
            await cls.filter(user_id=user_id)
            .order_by("-create_time")
            .limit(limit)
            .all()
        )

    @classmethod
    async def get_group_logs(
        cls, group_id: str, limit: int = 100
    ) -> list["BehaviorLog"]:
        """获取群组日志

        参数:
            group_id: 群组id
            limit: 返回数量限制

        返回:
            list[BehaviorLog]: 日志列表
        """
        return (
            await cls.filter(group_id=group_id)
            .order_by("-create_time")
            .limit(limit)
            .all()
        )

    @classmethod
    async def get_module_usage(
        cls, module: str, days: int = 7
    ) -> dict:
        """获取模块使用统计

        参数:
            module: 模块名
            days: 统计天数

        返回:
            dict: 统计信息
        """
        import time

        start_time = int(time.time()) - days * 86400
        logs = await cls.filter(module=module, create_time__gte=start_time).all()

        if not logs:
            return {"count": 0, "success": 0, "failed": 0, "ignored": 0}

        return {
            "count": len(logs),
            "success": sum(1 for log in logs if log.status == 0),
            "failed": sum(1 for log in logs if log.status == 1),
            "ignored": sum(1 for log in logs if log.status == 2),
        }

    @classmethod
    async def cleanup_old_logs(cls, days: int = 30) -> int:
        """清理旧日志

        参数:
            days: 保留天数

        返回:
            int: 删除数量
        """
        import time

        threshold = int(time.time()) - days * 86400
        deleted = await cls.filter(create_time__lt=threshold).delete()
        return deleted
