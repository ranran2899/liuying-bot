"""
定时任务数据模型
定义任务信息和相关数据结构
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypeAlias

from liuying.utils.apscheduler.constants import (
    DEFAULT_MAX_INSTANCES,
    DEFAULT_MISFIRE_GRACE_TIME,
    DEFAULT_PRIORITY,
)
from liuying.utils.enum import TaskStatus, TriggerType

# 类型别名
TriggerConfig: TypeAlias = dict[str, Any]
"""触发器配置字典"""
TaskFunc: TypeAlias = Callable[..., Any]
"""任务函数类型"""
TaskId: TypeAlias = str
"""任务ID类型"""


@dataclass(slots=True)
class TaskInfo:
    """
    任务信息数据类（统一任务模型）

    存储任务的完整信息，包括触发器配置、执行参数、状态等。
    作为 TaskEntry 和 Manager 层的统一数据结构。
    """

    id: str
    """任务ID"""
    name: str
    """任务名称"""
    trigger_type: TriggerType
    """触发器类型"""
    func: TaskFunc | None = None
    """任务函数"""
    status: TaskStatus = TaskStatus.PENDING
    """任务状态"""
    group: str = "default"
    """任务分组"""
    description: str = ""
    """任务描述"""
    trigger_config: TriggerConfig = field(default_factory=dict)
    """触发器配置"""
    max_instances: int = DEFAULT_MAX_INSTANCES
    """最大并发实例数"""
    args: tuple = field(default_factory=tuple)
    """位置参数"""
    kwargs: dict[str, Any] = field(default_factory=dict)
    """关键字参数"""
    created_at: datetime = field(default_factory=datetime.now)
    """创建时间"""
    last_run_time: datetime | None = None
    """上次运行时间"""
    run_count: int = 0
    """运行次数"""
    priority: int = DEFAULT_PRIORITY
    """优先级"""
    dependencies: list[str] = field(default_factory=list)
    """依赖任务列表"""
    misfire_grace_time: int | None = DEFAULT_MISFIRE_GRACE_TIME
    """错过执行的宽限时间（秒）"""
    save_to_db: bool = False
    """是否持久化到数据库"""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "id": self.id,
            "name": self.name,
            "trigger_type": self.trigger_type.value,
            "status": self.status.value,
            "group": self.group,
            "description": self.description,
            "trigger_config": self.trigger_config,
            "max_instances": self.max_instances,
            "args": self.args,
            "kwargs": self.kwargs,
            "created_at": self.created_at.isoformat(),
            "last_run_time": (
                self.last_run_time.isoformat() if self.last_run_time else None
            ),
            "run_count": self.run_count,
            "priority": self.priority,
            "dependencies": self.dependencies,
            "misfire_grace_time": self.misfire_grace_time,
            "save_to_db": self.save_to_db,
        }


@dataclass(slots=True)
class TaskConfig:
    """
    任务配置（统一配置对象）

    封装任务注册所需的全部参数，作为 _add_task 的统一入口。
    add_cron_task/add_interval_task/add_date_task 与对应装饰器
    构造此对象后委托 _add_task，消除参数列表重复。
    """

    task_id: str
    """任务ID"""
    name: str
    """任务名称"""
    trigger_type: TriggerType
    """触发器类型"""
    func: TaskFunc
    """任务函数"""
    trigger_config: TriggerConfig = field(default_factory=dict)
    """触发器配置"""
    group: str = "default"
    """任务分组"""
    description: str = ""
    """任务描述"""
    max_instances: int = DEFAULT_MAX_INSTANCES
    """最大并发实例数"""
    args: tuple = field(default_factory=tuple)
    """位置参数"""
    kwargs: dict[str, Any] = field(default_factory=dict)
    """关键字参数"""
    priority: int = DEFAULT_PRIORITY
    """优先级"""
    dependencies: list[str] = field(default_factory=list)
    """依赖任务列表"""
    misfire_grace_time: int | None = DEFAULT_MISFIRE_GRACE_TIME
    """错过执行的宽限时间（秒）"""
    replace_existing: bool = False
    """是否替换已存在的任务"""
    save_to_db: bool = False
    """是否持久化到数据库"""


@dataclass(slots=True)
class TaskExecutionLog:
    """
    任务执行日志

    记录任务的执行历史，包括执行时间、结果、错误信息等。
    """

    task_id: str
    """任务ID"""
    task_name: str
    """任务名称"""
    start_time: datetime
    """开始时间"""
    end_time: datetime | None = None
    """结束时间"""
    success: bool = False
    """是否成功"""
    error_message: str | None = None
    """错误信息"""
    result: Any = None
    """执行结果"""

    @property
    def duration(self) -> float | None:
        """执行耗时（秒）"""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "success": self.success,
            "error_message": self.error_message,
            "duration": self.duration,
        }


@dataclass(slots=True)
class TaskGroup:
    """
    任务分组

    用于组织和管理一组相关任务。
    """

    name: str
    """分组名称"""
    description: str = ""
    """分组描述"""
    task_ids: list[str] = field(default_factory=list)
    """任务ID列表"""
    created_at: datetime = field(default_factory=datetime.now)
    """创建时间"""

    def add_task(self, task_id: str) -> None:
        """添加任务到分组"""
        if task_id not in self.task_ids:
            self.task_ids.append(task_id)

    def remove_task(self, task_id: str) -> bool:
        """从分组移除任务"""
        if task_id in self.task_ids:
            self.task_ids.remove(task_id)
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "name": self.name,
            "description": self.description,
            "task_ids": self.task_ids,
            "created_at": self.created_at.isoformat(),
        }
