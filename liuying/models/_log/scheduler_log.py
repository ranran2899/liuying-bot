"""
调度器任务执行日志模型
用于持久化存储任务执行历史记录
"""

import json
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class SchedulerLog(Model):
    """
    调度器任务执行日志模型类

    用于持久化存储定时任务执行历史，支持查询、统计和分析
    """

    __tablename__ = "scheduler_log"
    __table_args__ = {"comment": "调度器任务执行日志表"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="自增id")
    """自增id"""
    log_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, comment="日志唯一标识")
    """日志唯一标识"""
    job_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True, comment="任务唯一标识符")
    """任务唯一标识符"""
    job_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="任务名称")
    """任务名称"""
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=True, comment="触发器类型")
    """触发器类型"""
    group: Mapped[str] = mapped_column(String(100), default="default", index=True, comment="任务分组")
    """任务分组"""
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True, comment="开始执行时间")
    """开始执行时间"""
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="结束执行时间")
    """结束执行时间"""
    duration: Mapped[float | None] = mapped_column(Float, nullable=True, comment="执行耗时(秒)")
    """执行耗时(秒)"""
    success: Mapped[bool] = mapped_column(Boolean, default=False, index=True, comment="是否执行成功")
    """是否执行成功"""
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="错误信息")
    """错误信息"""
    error_traceback: Mapped[str | None] = mapped_column(Text, nullable=True, comment="错误堆栈")
    """错误堆栈"""
    result_data: Mapped[str | None] = mapped_column(Text, nullable=True, comment="执行结果数据(JSON)")
    """执行结果数据"""
    retry_count: Mapped[int] = mapped_column(Integer, default=0, comment="重试次数")
    """重试次数"""
    timeout: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否超时")
    """是否超时"""
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    """创建时间"""

    @property
    def result(self) -> Any:
        """获取执行结果数据"""
        try:
            return json.loads(self.result_data) if self.result_data else None
        except json.JSONDecodeError:
            return None

    @result.setter
    def result(self, value: Any):
        """设置执行结果数据"""
        try:
            self.result_data = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            self.result_data = str(value)

    @classmethod
    async def create_log(
        cls,
        log_id: str,
        job_id: str,
        job_name: str,
        trigger_type: str | None = None,
        group: str = "default",
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        duration: float | None = None,
        success: bool = False,
        error_message: str | None = None,
        error_traceback: str | None = None,
        result_data: Any = None,
        retry_count: int = 0,
        timeout: bool = False,
    ) -> "SchedulerLog":
        """
        创建执行日志

        参数:
            log_id: 日志唯一标识
            job_id: 任务唯一标识符
            job_name: 任务名称
            trigger_type: 触发器类型
            group: 任务分组
            start_time: 开始执行时间
            end_time: 结束执行时间
            duration: 执行耗时(秒)
            success: 是否执行成功
            error_message: 错误信息
            error_traceback: 错误堆栈
            result_data: 执行结果数据
            retry_count: 重试次数
            timeout: 是否超时

        返回:
            SchedulerLog对象
        """
        log = await cls.create(
            log_id=log_id,
            job_id=job_id,
            job_name=job_name,
            trigger_type=trigger_type,
            group=group,
            start_time=start_time or datetime.now(),
            end_time=end_time,
            duration=duration,
            success=success,
            error_message=error_message,
            error_traceback=error_traceback,
            retry_count=retry_count,
            timeout=timeout,
        )
        if result_data is not None:
            log.result = result_data
            await log.save(update_fields=["result_data"])
        return log

    @classmethod
    async def get_logs_by_job_id(
        cls,
        job_id: str,
        limit: int = 100,
        offset: int = 0,
        success_only: bool = False,
    ) -> list["SchedulerLog"]:
        """
        根据任务ID获取执行日志

        参数:
            job_id: 任务唯一标识符
            limit: 返回数量限制
            offset: 偏移量
            success_only: 仅返回成功的日志

        返回:
            SchedulerLog对象列表
        """
        query = cls.filter(job_id=job_id)
        if success_only:
            query = query.filter(success=True)
        return await query.order_by("-start_time").limit(limit).offset(offset).all()

    @classmethod
    async def get_logs_by_group(
        cls,
        group: str,
        limit: int = 100,
        offset: int = 0,
        success_only: bool = False,
    ) -> list["SchedulerLog"]:
        """
        根据分组获取执行日志

        参数:
            group: 分组名称
            limit: 返回数量限制
            offset: 偏移量
            success_only: 仅返回成功的日志

        返回:
            SchedulerLog对象列表
        """
        query = cls.filter(group=group)
        if success_only:
            query = query.filter(success=True)
        return await query.order_by("-start_time").limit(limit).offset(offset).all()

    @classmethod
    async def get_statistics(
        cls,
        job_id: str | None = None,
        group: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, Any]:
        """
        获取执行统计数据

        参数:
            job_id: 任务唯一标识符(可选)
            group: 分组名称(可选)
            start_date: 开始日期(可选)
            end_date: 结束日期(可选)

        返回:
            统计数据字典
        """
        query = cls.filter()
        if job_id:
            query = query.filter(job_id=job_id)
        if group:
            query = query.filter(group=group)
        if start_date:
            query = query.where_gte("start_time", start_date)
        if end_date:
            query = query.where_lte("start_time", end_date)

        logs = await query.all()

        total_count = len(logs)
        success_count = sum(1 for log in logs if log.success)
        fail_count = total_count - success_count
        timeout_count = sum(1 for log in logs if log.timeout)
        avg_duration = (
            sum(log.duration for log in logs if log.duration is not None) / total_count
            if total_count > 0
            else 0
        )

        durations = [log.duration for log in logs if log.duration is not None]
        min_duration = min(durations) if durations else 0
        max_duration = max(durations) if durations else 0

        return {
            "total_count": total_count,
            "success_count": success_count,
            "fail_count": fail_count,
            "timeout_count": timeout_count,
            "success_rate": success_count / total_count if total_count > 0 else 0,
            "avg_duration": avg_duration,
            "min_duration": min_duration,
            "max_duration": max_duration,
        }

    @classmethod
    async def cleanup_old_logs(
        cls,
        days_to_keep: int = 30,
        max_logs_per_job: int = 1000,
    ) -> int:
        """
        清理旧日志

        参数:
            days_to_keep: 保留天数
            max_logs_per_job: 每个任务最多保留的日志数

        返回:
            删除的日志数量
        """
        from datetime import timedelta

        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        deleted_count = 0

        # 删除过期日志
        old_logs = await cls.filter().where_lt("start_time", cutoff_date).all()
        for log in old_logs:
            await log.delete()
            deleted_count += 1

        # 限制每个任务的日志数量
        job_ids = await cls.distinct("job_id").all()
        for job_id in job_ids:
            logs = await cls.filter(job_id=job_id).order_by("-start_time").all()
            if len(logs) > max_logs_per_job:
                for log in logs[max_logs_per_job:]:
                    await log.delete()
                    deleted_count += 1

        return deleted_count
