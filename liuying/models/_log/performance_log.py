from datetime import datetime
from typing import ClassVar

from sqlalchemy import BigInteger, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class PerformanceLog(Model):
    """性能日志模型类

    用于记录命令执行性能数据
    """

    __tablename__ = "performance_log"
    __table_args__: ClassVar[dict] = {
        "comment": "性能日志表，记录命令执行性能数据"
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    """自增id"""
    module: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="插件模块名"
    )
    """插件模块名"""
    user_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="用户id"
    )
    """用户id"""
    group_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="群组id"
    )
    """群组id"""
    execute_time: Mapped[float] = mapped_column(
        Float, nullable=False, comment="执行耗时（秒）"
    )
    """执行耗时（秒）"""
    hook_time: Mapped[float] = mapped_column(
        Float, default=0, comment="Hook耗时（秒）"
    )
    """Hook耗时（秒）"""
    status: Mapped[int] = mapped_column(
        Integer, default=0, comment="执行状态 0-成功 1-失败 2-超时"
    )
    """执行状态"""
    error_msg: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="错误信息"
    )
    """错误信息"""
    create_time: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="创建时间戳"
    )
    """创建时间戳"""

    @classmethod
    async def add_log(
        cls,
        module: str,
        user_id: str | None,
        group_id: str | None,
        execute_time: float,
        hook_time: float = 0,
        status: int = 0,
        error_msg: str | None = None,
    ) -> "PerformanceLog":
        """添加性能日志

        参数:
            module: 模块名
            user_id: 用户id
            group_id: 群组id
            execute_time: 执行耗时
            hook_time: Hook耗时
            status: 状态
            error_msg: 错误信息

        返回:
            PerformanceLog: 日志对象
        """
        import time

        return await cls.create(
            module=module,
            user_id=user_id,
            group_id=group_id,
            execute_time=execute_time,
            hook_time=hook_time,
            status=status,
            error_msg=error_msg,
            create_time=int(time.time()),
        )

    @classmethod
    async def get_slow_commands(
        cls, threshold: float = 5.0, limit: int = 100
    ) -> list["PerformanceLog"]:
        """获取慢命令列表

        参数:
            threshold: 耗时阈值（秒）
            limit: 返回数量限制

        返回:
            list[PerformanceLog]: 慢命令列表
        """
        return (
            await cls.filter(execute_time__gte=threshold)
            .order_by("-execute_time")
            .limit(limit)
            .all()
        )

    @classmethod
    async def get_module_stats(
        cls, module: str, days: int = 7
    ) -> dict:
        """获取模块统计信息

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
            return {
                "count": 0,
                "avg_time": 0,
                "max_time": 0,
                "min_time": 0,
                "error_rate": 0,
            }

        times = [log.execute_time for log in logs]
        errors = sum(1 for log in logs if log.status != 0)

        return {
            "count": len(logs),
            "avg_time": sum(times) / len(times),
            "max_time": max(times),
            "min_time": min(times),
            "error_rate": errors / len(logs) * 100,
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
