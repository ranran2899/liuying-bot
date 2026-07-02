"""
任务分组管理 Mixin
负责任务分组的暂停、恢复和查询
"""

from typing import TYPE_CHECKING

from liuying.utils.apscheduler.mixins.base import TaskManagerBaseMixin
from liuying.utils.log import logger

if TYPE_CHECKING:
    from liuying.utils.apscheduler.models import TaskInfo


class TaskGroupMixin(TaskManagerBaseMixin):
    """
    任务分组管理 Mixin

    提供：
    - 分组暂停/恢复
    - 分组任务查询
    - 分组列表获取
    """

    async def pause_group(self, group: str, update_db: bool = True) -> int:
        """暂停指定分组的所有任务

        Args:
            group: 分组名称
            update_db: 是否更新数据库

        Returns:
            已暂停的任务数量
        """
        tasks = self.get_tasks_by_group(group)
        count = 0
        for task in tasks:
            if await self.pause_task(task.id, update_db=update_db):
                count += 1
        logger.info(f"暂停分组 '{group}' 中的 {count} 个任务")
        return count

    async def resume_group(self, group: str, update_db: bool = True) -> int:
        """恢复指定分组的所有任务

        Args:
            group: 分组名称
            update_db: 是否更新数据库

        Returns:
            已恢复的任务数量
        """
        tasks = self.get_tasks_by_group(group)
        count = 0
        for task in tasks:
            if await self.resume_task(task.id, update_db=update_db):
                count += 1
        logger.info(f"恢复分组 '{group}' 中的 {count} 个任务")
        return count

    def get_tasks_by_group(self, group: str) -> list["TaskInfo"]:
        """获取指定分组的所有任务

        Args:
            group: 分组名称

        Returns:
            任务信息列表
        """
        if group not in self._groups:
            return []
        return [
            self._tasks[task_id]
            for task_id in self._groups[group]
            if task_id in self._tasks
        ]

    def get_groups(self) -> list[str]:
        """获取所有分组名称

        Returns:
            分组名称列表
        """
        return list(self._groups.keys())
