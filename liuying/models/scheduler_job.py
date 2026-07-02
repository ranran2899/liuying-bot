"""
调度器任务存储模型
"""

import json
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class SchedulerJob(Model):
    """
    调度器任务模型类

    用于持久化存储定时任务信息，支持任务恢复和持久化
    """

    __tablename__ = "scheduler_job"
    __table_args__ = {"comment": "调度器任务表，用于持久化存储定时任务信息"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="自增id")
    """自增id"""
    job_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, comment="任务唯一标识符")
    """任务唯一标识符"""
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="任务名称")
    """任务名称"""
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="触发器类型(cron/interval/date)")
    """触发器类型"""
    trigger_args: Mapped[str] = mapped_column(Text, nullable=False, comment="触发器参数(JSON格式)")
    """触发器参数"""
    group: Mapped[str] = mapped_column(String(100), default="default", comment="任务分组")
    """任务分组"""
    description: Mapped[str] = mapped_column(Text, default="", comment="任务描述")
    """任务描述"""
    next_run_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="下次运行时间")
    """下次运行时间"""
    previous_run_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="上次运行时间")
    """上次运行时间"""
    max_instances: Mapped[int] = mapped_column(default=1, comment="最大并发实例数")
    """最大并发实例数"""
    coalesce: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否合并错过的任务")
    """是否合并错过的任务"""
    misfire_grace_time: Mapped[int] = mapped_column(default=30, comment="错过执行的宽限时间(秒)")
    """错过执行的宽限时间"""
    paused: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否暂停")
    """是否暂停"""
    pause_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="暂停到指定时间")
    """暂停到指定时间"""
    pause_reason: Mapped[str | None] = mapped_column(Text, nullable=True, comment="暂停原因")
    """暂停原因"""
    running_instances: Mapped[int] = mapped_column(default=0, comment="当前运行实例数")
    """当前运行实例数"""
    run_count: Mapped[int] = mapped_column(default=0, comment="运行次数")
    """运行次数"""
    success_count: Mapped[int] = mapped_column(default=0, comment="成功次数")
    """成功次数"""
    fail_count: Mapped[int] = mapped_column(default=0, comment="失败次数")
    """失败次数"""
    timeout: Mapped[float | None] = mapped_column(Float, nullable=True, comment="任务超时时间(秒)")
    """任务超时时间(秒)"""
    timezone: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="时区")
    """时区"""
    priority: Mapped[int] = mapped_column(default=10, comment="任务优先级")
    """任务优先级"""
    retry_max_attempts: Mapped[int] = mapped_column(default=0, comment="最大重试次数")
    """最大重试次数"""
    retry_delay: Mapped[float] = mapped_column(default=1.0, comment="重试延迟(秒)")
    """重试延迟(秒)"""
    retry_exponential_backoff: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否指数退避")
    """是否指数退避"""
    func_module: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="函数模块路径")
    """函数模块路径"""
    func_name: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="函数名称")
    """函数名称"""
    args: Mapped[str] = mapped_column(Text, default="[]", comment="位置参数(JSON格式)")
    """位置参数"""
    kwargs: Mapped[str] = mapped_column(Text, default="{}", comment="关键字参数(JSON格式)")
    """关键字参数"""
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    """创建时间"""
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    """更新时间"""

    @property
    def trigger_args_dict(self) -> dict:
        """获取触发器参数字典"""
        try:
            return json.loads(self.trigger_args) if self.trigger_args else {}
        except json.JSONDecodeError:
            return {}

    @trigger_args_dict.setter
    def trigger_args_dict(self, value: dict):
        """设置触发器参数字典"""
        self.trigger_args = json.dumps(value, ensure_ascii=False)

    @property
    def args_list(self) -> list:
        """获取位置参数列表"""
        try:
            return json.loads(self.args) if self.args else []
        except json.JSONDecodeError:
            return []

    @args_list.setter
    def args_list(self, value: list):
        """设置位置参数列表"""
        self.args = json.dumps(value, ensure_ascii=False)

    @property
    def kwargs_dict(self) -> dict:
        """获取关键字参数字典"""
        try:
            return json.loads(self.kwargs) if self.kwargs else {}
        except json.JSONDecodeError:
            return {}

    @kwargs_dict.setter
    def kwargs_dict(self, value: dict):
        """设置关键字参数字典"""
        self.kwargs = json.dumps(value, ensure_ascii=False)

    @classmethod
    async def get_by_job_id(cls, job_id: str) -> "SchedulerJob | None":
        """
        根据任务ID获取任务信息

        参数:
            job_id: 任务唯一标识符

        返回:
            SchedulerJob对象或None
        """
        return await cls.filter(job_id=job_id).first()

    @classmethod
    async def get_active_jobs(cls) -> list["SchedulerJob"]:
        """
        获取所有活跃任务（未暂停的任务）

        返回:
            SchedulerJob对象列表
        """
        return await cls.filter(paused=False).all()

    @classmethod
    async def get_jobs_by_group(cls, group: str) -> list["SchedulerJob"]:
        """
        根据分组获取任务列表

        参数:
            group: 分组名称

        返回:
            SchedulerJob对象列表
        """
        return await cls.filter(group=group).all()

    @classmethod
    async def get_all_groups(cls) -> list[str]:
        """
        获取所有分组名称

        返回:
            分组名称列表
        """
        jobs = await cls.filter().all()
        return list({job.group for job in jobs if job.group})

    @classmethod
    async def create_job(
        cls,
        job_id: str,
        name: str,
        trigger_type: str,
        trigger_args: dict,
        group: str = "default",
        description: str = "",
        max_instances: int = 1,
        func_module: str | None = None,
        func_name: str | None = None,
        args: list | None = None,
        kwargs: dict | None = None,
        timeout: float | None = None,
        timezone: str | None = None,
        priority: int = 10,
        retry_max_attempts: int = 0,
        retry_delay: float = 1.0,
        retry_exponential_backoff: bool = True,
    ) -> "SchedulerJob":
        """
        创建任务记录

        参数:
            job_id: 任务唯一标识符
            name: 任务名称
            trigger_type: 触发器类型
            trigger_args: 触发器参数
            group: 任务分组
            description: 任务描述
            max_instances: 最大并发实例数
            func_module: 函数模块路径
            func_name: 函数名称
            args: 位置参数
            kwargs: 关键字参数
            timeout: 任务超时时间
            timezone: 时区
            priority: 任务优先级
            retry_max_attempts: 最大重试次数
            retry_delay: 重试延迟
            retry_exponential_backoff: 是否指数退避

        返回:
            SchedulerJob对象
        """
        job = await cls.create(
            job_id=job_id,
            name=name,
            trigger_type=trigger_type,
            trigger_args=json.dumps(trigger_args, ensure_ascii=False),
            group=group,
            description=description,
            max_instances=max_instances,
            func_module=func_module,
            func_name=func_name,
            args=json.dumps(args or [], ensure_ascii=False),
            kwargs=json.dumps(kwargs or {}, ensure_ascii=False),
            timeout=timeout,
            timezone=timezone,
            priority=priority,
            retry_max_attempts=retry_max_attempts,
            retry_delay=retry_delay,
            retry_exponential_backoff=retry_exponential_backoff,
        )
        return job

    @classmethod
    async def update_job_status(cls, job_id: str, paused: bool) -> bool:
        """
        更新任务暂停状态

        参数:
            job_id: 任务唯一标识符
            paused: 是否暂停

        返回:
            是否更新成功
        """
        job = await cls.get_by_job_id(job_id)
        if job:
            job.paused = paused
            await job.save(update_fields=["paused", "updated_at"])
            return True
        return False

    @classmethod
    async def pause_job_until(
        cls,
        job_id: str,
        pause_until: datetime,
        reason: str | None = None,
    ) -> bool:
        """
        暂停任务到指定时间

        参数:
            job_id: 任务唯一标识符
            pause_until: 暂停到的时间
            reason: 暂停原因

        返回:
            是否更新成功
        """
        job = await cls.get_by_job_id(job_id)
        if job:
            job.paused = True
            job.pause_until = pause_until
            job.pause_reason = reason
            await job.save(update_fields=["paused", "pause_until", "pause_reason", "updated_at"])
            return True
        return False

    @classmethod
    async def increment_run_count(
        cls,
        job_id: str,
        success: bool = True,
    ) -> bool:
        """
        增加运行次数

        参数:
            job_id: 任务唯一标识符
            success: 是否成功

        返回:
            是否更新成功
        """
        job = await cls.get_by_job_id(job_id)
        if job:
            job.run_count += 1
            job.previous_run_time = datetime.now()
            if success:
                job.success_count += 1
            else:
                job.fail_count += 1
            await job.save(
                update_fields=[
                    "run_count",
                    "success_count",
                    "fail_count",
                    "previous_run_time",
                    "updated_at",
                ]
            )
            return True
        return False

    @classmethod
    async def delete_job(cls, job_id: str) -> bool:
        """
        删除任务记录

        参数:
            job_id: 任务唯一标识符

        返回:
            是否删除成功
        """
        job = await cls.get_by_job_id(job_id)
        if job:
            await job.delete()
            return True
        return False

    def to_dict(self, include_secret: bool = False) -> dict[str, Any]:
        """
        转换为字典格式

        参数:
            include_secret: 是否包含敏感信息

        返回:
            字典格式的任务信息
        """
        data = {
            "job_id": self.job_id,
            "name": self.name,
            "trigger_type": self.trigger_type,
            "trigger_args": self.trigger_args_dict,
            "group": self.group,
            "description": self.description,
            "max_instances": self.max_instances,
            "paused": self.paused,
            "priority": self.priority,
            "timeout": self.timeout,
            "timezone": self.timezone,
            "retry_max_attempts": self.retry_max_attempts,
            "retry_delay": self.retry_delay,
            "retry_exponential_backoff": self.retry_exponential_backoff,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_secret:
            data.update({
                "func_module": self.func_module,
                "func_name": self.func_name,
                "args": self.args_list,
                "kwargs": self.kwargs_dict,
            })
        return data

    @classmethod
    async def from_dict(cls, data: dict[str, Any]) -> "SchedulerJob | None":
        """
        从字典创建任务

        参数:
            data: 字典格式的任务信息

        返回:
            SchedulerJob对象
        """
        existing = await cls.get_by_job_id(data.get("job_id", ""))
        if existing:
            return None

        job = await cls.create_job(
            job_id=data["job_id"],
            name=data["name"],
            trigger_type=data["trigger_type"],
            trigger_args=data["trigger_args"],
            group=data.get("group", "default"),
            description=data.get("description", ""),
            max_instances=data.get("max_instances", 1),
            func_module=data.get("func_module"),
            func_name=data.get("func_name"),
            args=data.get("args"),
            kwargs=data.get("kwargs"),
            timeout=data.get("timeout"),
            timezone=data.get("timezone"),
            priority=data.get("priority", 10),
            retry_max_attempts=data.get("retry_max_attempts", 0),
            retry_delay=data.get("retry_delay", 1.0),
            retry_exponential_backoff=data.get("retry_exponential_backoff", True),
        )
        if data.get("paused"):
            job.paused = True
            await job.save(update_fields=["paused"])
        return job

    @classmethod
    def _run_script(cls):
        """数据库迁移脚本"""
        return [
            "ALTER TABLE scheduler_job ADD name VARCHAR(255) DEFAULT '';",
            "ALTER TABLE scheduler_job ADD group VARCHAR(100) DEFAULT 'default';",
            "ALTER TABLE scheduler_job ADD description TEXT DEFAULT '';",
            "ALTER TABLE scheduler_job ADD run_count INTEGER DEFAULT 0;",
            "ALTER TABLE scheduler_job ADD func_module VARCHAR(255);",
            "ALTER TABLE scheduler_job ADD func_name VARCHAR(255);",
            "ALTER TABLE scheduler_job ADD args TEXT DEFAULT '[]';",
            "ALTER TABLE scheduler_job ADD kwargs TEXT DEFAULT '{}';",
            "ALTER TABLE scheduler_job ADD pause_until DATETIME;",
            "ALTER TABLE scheduler_job ADD pause_reason TEXT;",
            "ALTER TABLE scheduler_job ADD success_count INTEGER DEFAULT 0;",
            "ALTER TABLE scheduler_job ADD fail_count INTEGER DEFAULT 0;",
            "ALTER TABLE scheduler_job ADD timeout FLOAT;",
            "ALTER TABLE scheduler_job ADD timezone VARCHAR(100);",
            "ALTER TABLE scheduler_job ADD priority INTEGER DEFAULT 10;",
            "ALTER TABLE scheduler_job ADD retry_max_attempts INTEGER DEFAULT 0;",
            "ALTER TABLE scheduler_job ADD retry_delay FLOAT DEFAULT 1.0;",
            "ALTER TABLE scheduler_job ADD retry_exponential_backoff BOOLEAN DEFAULT TRUE;",
        ]
