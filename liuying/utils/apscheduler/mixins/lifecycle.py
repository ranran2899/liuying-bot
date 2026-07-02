"""
任务生命周期管理 Mixin
负责任务的移除、暂停、恢复、修改和立即执行
"""

from typing import Any

from liuying.models.scheduler_job import SchedulerJob
from liuying.utils.apscheduler.mixins.base import TaskManagerBaseMixin
from liuying.utils.apscheduler.models import TaskInfo
from liuying.utils.apscheduler.triggers import trigger_factory
from liuying.utils.enum import TaskStatus, TriggerType
from liuying.utils.log import logger


class TaskLifecycleMixin(TaskManagerBaseMixin):
    """
    任务生命周期管理 Mixin

    提供:
    - 任务移除
    - 任务暂停/恢复
    - 任务修改
    - 立即执行任务
    """

    def _get_task_or_warn(self, task_id: str) -> TaskInfo | None:
        """获取任务,不存在则警告并返回 None

        参数:
            task_id: 任务唯一标识

        返回:
            任务信息对象,不存在返回 None
        """
        task = self._tasks.get(task_id)
        if task is None:
            logger.warning(f"任务 '{task_id}' 不存在")
        return task

    async def remove_task(
        self, task_id: str, delete_from_db: bool = True
    ) -> bool:
        """移除指定任务

        参数:
            task_id: 任务唯一标识
            delete_from_db: 是否从数据库删除

        返回:
            是否移除成功
        """
        task_info = self._get_task_or_warn(task_id)
        if task_info is None:
            return False

        group = task_info.group

        try:
            self._scheduler.remove_task(task_id)
            del self._tasks[task_id]

            if group in self._groups and task_id in self._groups[group]:
                self._groups[group].remove(task_id)
                if not self._groups[group]:
                    del self._groups[group]

            if delete_from_db:
                await SchedulerJob.delete_job(task_id)

            logger.info(f"移除定时任务: {task_info.name}({task_id})")
            return True
        except Exception as e:
            logger.error(f"移除任务 '{task_id}' 失败", e=e)
            return False

    async def pause_task(
        self, task_id: str, update_db: bool = True
    ) -> bool:
        """暂停指定任务

        参数:
            task_id: 任务唯一标识
            update_db: 是否更新数据库

        返回:
            是否暂停成功
        """
        task_info = self._get_task_or_warn(task_id)
        if task_info is None:
            return False

        try:
            self._scheduler.pause_task(task_id)
            task_info.status = TaskStatus.PAUSED

            if update_db:
                await SchedulerJob.update_job_status(task_id, paused=True)

            logger.info(f"暂停定时任务: {task_info.name}({task_id})")
            return True
        except Exception as e:
            logger.error(f"暂停任务 '{task_id}' 失败", e=e)
            return False

    async def resume_task(
        self, task_id: str, update_db: bool = True
    ) -> bool:
        """恢复指定任务

        参数:
            task_id: 任务唯一标识
            update_db: 是否更新数据库

        返回:
            是否恢复成功
        """
        task_info = self._get_task_or_warn(task_id)
        if task_info is None:
            return False

        try:
            self._scheduler.resume_task(task_id)
            task_info.status = TaskStatus.RUNNING

            if update_db:
                await SchedulerJob.update_job_status(task_id, paused=False)

            logger.info(f"恢复定时任务: {task_info.name}({task_id})")
            return True
        except Exception as e:
            logger.error(f"恢复任务 '{task_id}' 失败", e=e)
            return False

    def modify_task(
        self,
        task_id: str,
        *,
        trigger_type: str | None = None,
        trigger_config: dict[str, Any] | None = None,
        name: str | None = None,
        group: str | None = None,
        priority: int | None = None,
        max_instances: int | None = None,
        description: str | None = None,
        misfire_grace_time: int | None | bool = None,
    ) -> bool:
        """修改任务配置(显式签名,与 scheduler.py 统一)

        参数:
            task_id: 任务唯一标识
            trigger_type: 触发器类型(cron/interval/date)
            trigger_config: 触发器配置
            name: 任务名称
            group: 任务分组
            priority: 任务优先级
            max_instances: 最大并发实例数
            description: 任务描述
            misfire_grace_time: 错过执行的宽限时间

        返回:
            是否修改成功
        """
        task_info = self._get_task_or_warn(task_id)
        if task_info is None:
            return False

        try:
            new_trigger = None
            new_trigger_type_enum: TriggerType | None = None

            if trigger_type and trigger_config:
                new_trigger_type_enum = TriggerType(trigger_type)
                new_trigger = trigger_factory.create(
                    trigger_type, trigger_config
                )

            self._scheduler.modify_task(
                task_id,
                trigger=new_trigger,
                trigger_type=new_trigger_type_enum,
                trigger_config=trigger_config,
                name=name,
                group=group,
                priority=priority,
                max_instances=max_instances,
                description=description,
                misfire_grace_time=misfire_grace_time,
            )

            if new_trigger_type_enum:
                task_info.trigger_type = new_trigger_type_enum
            if trigger_config:
                task_info.trigger_config.update(trigger_config)

            for field_name, value in [
                ("name", name),
                ("group", group),
                ("priority", priority),
                ("max_instances", max_instances),
                ("description", description),
            ]:
                if value is not None:
                    setattr(task_info, field_name, value)

            if misfire_grace_time is not None and misfire_grace_time is not False:
                task_info.misfire_grace_time = misfire_grace_time

            logger.info(f"修改定时任务: {task_info.name}({task_id})")
            return True
        except Exception as e:
            logger.error(f"修改任务 '{task_id}' 失败", e=e)
            return False

    def run_task_now(self, task_id: str) -> bool:
        """立即执行指定任务(不等待触发器)

        参数:
            task_id: 任务唯一标识

        返回:
            是否执行成功
        """
        task_info = self._get_task_or_warn(task_id)
        if task_info is None:
            return False

        try:
            self._scheduler.run_task_now(task_id)
            logger.info(f"立即执行定时任务: {task_info.name}({task_id})")
            return True
        except Exception as e:
            logger.error(f"立即执行任务 '{task_id}' 失败", e=e)
            return False
