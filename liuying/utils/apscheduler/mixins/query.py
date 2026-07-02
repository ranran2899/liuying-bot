"""
任务查询 Mixin
负责任务信息的查询和检查
"""

from typing import TYPE_CHECKING

from liuying.utils.apscheduler.mixins.base import TaskManagerBaseMixin

if TYPE_CHECKING:
    from liuying.utils.apscheduler.models import TaskInfo


class TaskQueryMixin(TaskManagerBaseMixin):
    """
    任务查询 Mixin

    提供：
    - 单任务查询
    - 全部任务查询
    - 任务存在性检查
    """

    def get_task(self, task_id: str) -> "TaskInfo | None":
        """获取指定任务信息

        Args:
            task_id: 任务唯一标识

        Returns:
            任务信息对象，不存在返回None
        """
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> list["TaskInfo"]:
        """获取所有任务信息

        Returns:
            任务信息列表
        """
        return list(self._tasks.values())

    def task_exists(self, task_id: str) -> bool:
        """检查任务是否存在

        Args:
            task_id: 任务唯一标识

        Returns:
            任务是否存在
        """
        return task_id in self._tasks
