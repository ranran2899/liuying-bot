"""
任务管理器 Mixin 基类

定义 Mixin 的公共接口和类型约定，所有 Mixin 应继承此类。
运行时通过 TaskManager 实例访问 _scheduler、_tasks、_groups 等属性；
_tasks 直接持有调度器创建的 TaskEntry，为运行时状态的单一数据源。
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..scheduler import Scheduler, TaskEntry


class TaskManagerBaseMixin:
    """
    任务管理器 Mixin 基类

    提供类型约定，所有 Mixin 应继承此类。
    运行时通过 TaskManager 实例访问 _scheduler、_tasks、_groups 等属性。
    """

    _scheduler: "Scheduler"
    _tasks: dict[str, "TaskEntry"]
    _groups: dict[str, list[str]]
    _started: bool
