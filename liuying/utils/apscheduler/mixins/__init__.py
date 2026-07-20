"""
任务管理器 Mixin 模块

提供职责分离的任务管理功能，通过组合 Mixin 实现完整的任务管理器。
"""

from .base import TaskManagerBaseMixin
from .decorator import TaskDecoratorMixin
from .group import TaskGroupMixin
from .lifecycle import TaskLifecycleMixin
from .persistence import TaskPersistenceMixin
from .query import TaskQueryMixin
from .registration import TaskRegistrationMixin

__all__ = [
    "TaskDecoratorMixin",
    "TaskGroupMixin",
    "TaskLifecycleMixin",
    "TaskManagerBaseMixin",
    "TaskPersistenceMixin",
    "TaskQueryMixin",
    "TaskRegistrationMixin",
]
