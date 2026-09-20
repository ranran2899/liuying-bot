"""
定时任务数据模型

定义任务信息、任务配置等数据结构，作为各模块间传递任务的统一载体。
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from liuying.utils.enum import TaskStatus, TriggerType

from .constants import (
    DEFAULT_MAX_INSTANCES,
    DEFAULT_MISFIRE_GRACE_TIME,
    DEFAULT_PRIORITY,
)

type TriggerConfig = dict[str, Any]
"""触发器配置字典"""
type TaskFunc = Callable[..., Any]
"""任务函数类型"""


@dataclass(slots=True)
class TaskInfo:
    """
    任务信息数据类（统一任务模型）

    存储任务的完整信息，包括触发器配置、执行参数、状态等。
    TaskEntry 继承本类并添加调度器运行时属性，
    管理器与调度器共享同一个 TaskEntry 实例（单一数据源）。
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
    args: tuple[Any, ...] = field(default_factory=tuple)
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


@dataclass(slots=True, kw_only=True)
class TaskConfig:
    """
    任务配置（统一配置对象）

    封装任务注册所需的全部参数，作为 add 任务的统一入口。
    add_cron/add_interval/add_date 与对应装饰器
    构造此对象后委托 _add_task，消除参数列表重复。
    全部字段关键字构造，task_id/name 允许为空并在
    _add_task 中自动补全。
    """

    task_id: str | None = None
    """任务ID，传 None 或空字符串时自动生成"""
    name: str | None = None
    """任务名称，为空时自动取 task_id"""
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
    args: tuple[Any, ...] = field(default_factory=tuple)
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
