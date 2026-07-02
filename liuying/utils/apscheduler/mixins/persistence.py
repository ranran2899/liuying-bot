"""
任务持久化 Mixin
负责任务的数据库持久化、恢复和动态函数加载
"""

import asyncio
from collections.abc import Callable
from datetime import datetime
from importlib import import_module
from typing import Any

from liuying.models.scheduler_job import SchedulerJob
from liuying.utils.apscheduler.mixins.base import TaskManagerBaseMixin
from liuying.utils.apscheduler.models import TaskConfig
from liuying.utils.apscheduler.triggers import trigger_factory
from liuying.utils.apscheduler.triggers.base import BaseTrigger
from liuying.utils.enum import TaskStatus, TriggerType
from liuying.utils.log import logger


class TaskPersistenceMixin(TaskManagerBaseMixin):
    """
    任务持久化 Mixin

    提供:
    - 任务保存到数据库
    - 从数据库恢复任务
    - 动态函数加载
    - 过期一次性任务处理
    """

    async def _save_to_db(
        self,
        task_id: str,
        name: str,
        trigger_type: TriggerType,
        trigger_config: dict[str, Any],
        group: str = "default",
        description: str = "",
        max_instances: int = 1,
        args: tuple | None = None,
        kwargs: dict[str, Any] | None = None,
        func: Callable | None = None,
        priority: int = 10,
    ) -> None:
        """保存任务到数据库

        参数:
            task_id: 任务唯一标识
            name: 任务名称
            trigger_type: 触发器类型
            trigger_config: 触发器配置
            group: 任务分组
            description: 任务描述
            max_instances: 最大并发实例数
            args: 任务位置参数
            kwargs: 任务关键字参数
            func: 任务执行函数
            priority: 任务优先级
        """
        func_module = func.__module__ if func else None
        func_name = func.__name__ if func else None

        existing = await SchedulerJob.get_by_job_id(task_id)
        if existing:
            existing.name = name
            existing.trigger_type = trigger_type.value
            existing.trigger_args_dict = trigger_config
            existing.group = group
            existing.description = description
            existing.max_instances = max_instances
            existing.priority = priority
            existing.func_module = func_module
            existing.func_name = func_name
            existing.args_list = list(args or [])
            existing.kwargs_dict = kwargs or {}
            await existing.save()
        else:
            await SchedulerJob.create_job(
                job_id=task_id,
                name=name,
                trigger_type=trigger_type.value,
                trigger_args=trigger_config,
                group=group,
                description=description,
                max_instances=max_instances,
                func_module=func_module,
                func_name=func_name,
                args=list(args or []),
                kwargs=kwargs or {},
                priority=priority,
            )

    def _get_func(
        self, func_module: str | None, func_name: str | None
    ) -> Callable | None:
        """动态加载函数

        参数:
            func_module: 函数模块名
            func_name: 函数名

        返回:
            加载的函数对象,失败返回None
        """
        if not func_module or not func_name:
            return None

        try:
            module = import_module(func_module)
            return getattr(module, func_name)
        except Exception as e:
            logger.error(f"加载函数 {func_module}.{func_name} 失败", e=e)
            return None

    async def _handle_expired_date_task(
        self, job: SchedulerJob, func: Callable
    ) -> bool:
        """处理过期的一次性任务

        参数:
            job: 任务数据对象
            func: 任务执行函数

        返回:
            是否执行了过期任务
        """
        try:
            run_date_str = job.trigger_args_dict.get("run_date")
            if not run_date_str:
                return False

            run_date = BaseTrigger._parse_datetime(run_date_str)

            if run_date > datetime.now():
                return False

            logger.info(
                f"检测到过期的一次性任务: {job.name}({job.job_id}), "
                f"计划执行时间: {run_date}, 立即执行"
            )

            try:
                result = func(*job.args_list, **job.kwargs_dict)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"执行过期任务 {job.job_id} 失败", e=e)

            await job.delete()
            return True
        except Exception as e:
            logger.error(f"处理过期任务 {job.job_id} 时发生错误", e=e)
            return False

    async def restore_tasks(self) -> int:
        """从数据库恢复任务到调度器

        返回:
            成功恢复的任务数量
        """
        jobs = await SchedulerJob.filter().all()
        restored_count = 0
        deleted_count = 0
        executed_count = 0

        for job in jobs:
            func = self._get_func(job.func_module, job.func_name)
            if not func:
                logger.warning(
                    f"任务 {job.job_id} 的函数不存在,已删除该任务"
                )
                await job.delete()
                deleted_count += 1
                continue

            try:
                if job.trigger_type == TriggerType.DATE.value:
                    executed = await self._handle_expired_date_task(job, func)
                    if executed:
                        executed_count += 1
                        continue

                config = TaskConfig(
                    task_id=job.job_id,
                    name=job.name,
                    trigger_type=TriggerType(job.trigger_type),
                    func=func,
                    trigger_config=job.trigger_args_dict,
                    group=job.group,
                    description=job.description,
                    max_instances=job.max_instances,
                    args=tuple(job.args_list),
                    kwargs=job.kwargs_dict,
                    priority=job.priority,
                    misfire_grace_time=job.misfire_grace_time,
                    replace_existing=True,
                    save_to_db=True,
                )

                task_info = self._register_task(config)
                trigger = trigger_factory.create(
                    job.trigger_type, job.trigger_args_dict
                )

                self._scheduler.add_task(
                    task_id=config.task_id,
                    name=config.name,
                    trigger=trigger,
                    func=func,
                    trigger_type=config.trigger_type,
                    trigger_config=config.trigger_config,
                    args=config.args,
                    kwargs=config.kwargs,
                    group=config.group,
                    priority=config.priority,
                    description=config.description,
                    max_instances=config.max_instances,
                    misfire_grace_time=config.misfire_grace_time,
                    replace_existing=True,
                    save_to_db=True,
                )

                if job.paused:
                    self._scheduler.pause_task(job.job_id)
                    task_info.status = TaskStatus.PAUSED

                task_info.created_at = job.created_at
                task_info.last_run_time = job.previous_run_time
                task_info.run_count = job.run_count

                restored_count += 1
            except Exception as e:
                logger.error(f"恢复任务 {job.job_id} 失败", e=e)

        if deleted_count > 0:
            logger.debug(f"已清理 {deleted_count} 个无效任务")
        if executed_count > 0:
            logger.info(f"已执行 {executed_count} 个过期的一次性任务")
        logger.debug(f"从数据库恢复 {restored_count} 个定时任务")
        return restored_count
