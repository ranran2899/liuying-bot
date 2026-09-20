"""
任务持久化 Mixin

负责任务的数据库持久化、恢复和动态函数加载。
"""

import asyncio
from collections.abc import Callable
from datetime import datetime
from importlib import import_module

from liuying.models.scheduler_job import SchedulerJob
from liuying.utils.enum import TriggerType
from liuying.utils.log import logger

from ..models import TaskConfig
from ..triggers.base import BaseTrigger
from .base import TaskManagerBaseMixin

_LOG_COMMAND = "SchedulerPersistence"


class TaskPersistenceMixin(TaskManagerBaseMixin):
    """
    任务持久化 Mixin

    提供:
    - 任务保存到数据库
    - 从数据库恢复任务
    - 动态函数加载
    - 过期一次性任务处理
    """

    async def _save_to_db(self, config: TaskConfig) -> None:
        """保存任务到数据库

        参数:
            config: 任务配置对象
        """
        func = config.func
        func_module = func.__module__ if func else None
        func_name = func.__name__ if func else None

        existing = await SchedulerJob.get_by_job_id(config.task_id)
        if existing:
            existing.name = config.name
            existing.trigger_type = config.trigger_type.value
            existing.trigger_args_dict = config.trigger_config
            existing.group = config.group
            existing.description = config.description
            existing.max_instances = config.max_instances
            existing.priority = config.priority
            existing.func_module = func_module
            existing.func_name = func_name
            existing.args_list = list(config.args)
            existing.kwargs_dict = config.kwargs
            await existing.save()
        else:
            await SchedulerJob.create_job(
                job_id=config.task_id,
                name=config.name,
                trigger_type=config.trigger_type.value,
                trigger_args=config.trigger_config,
                group=config.group,
                description=config.description,
                max_instances=config.max_instances,
                func_module=func_module,
                func_name=func_name,
                args=list(config.args),
                kwargs=config.kwargs,
                priority=config.priority,
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
            logger.error(
                f"加载函数 {func_module}.{func_name} 失败",
                _LOG_COMMAND,
                e=e,
            )
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
        run_date_str = job.trigger_args_dict.get("run_date")
        if not run_date_str:
            return False

        run_date = BaseTrigger.parse_datetime(run_date_str)
        if run_date > datetime.now():
            return False

        logger.info(
            f"检测到过期的一次性任务: {job.name}({job.job_id}), "
            f"计划执行时间: {run_date}, 立即执行",
            _LOG_COMMAND,
        )

        try:
            result = func(*job.args_list, **job.kwargs_dict)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.error(
                f"执行过期任务 {job.job_id} 失败",
                _LOG_COMMAND,
                e=e,
            )

        await job.delete()
        return True

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
                    f"任务 {job.job_id} 的函数不存在,已删除该任务",
                    _LOG_COMMAND,
                )
                await job.delete()
                deleted_count += 1
                continue

            try:
                if job.trigger_type == TriggerType.DATE.value:
                    if await self._handle_expired_date_task(job, func):
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

                # 恢复时跳过持久化，避免启动阶段重复写库
                task_info = await self._add_task(config, save_to_db=False)

                if job.paused:
                    self._scheduler.pause_task(job.job_id)

                task_info.created_at = job.created_at or task_info.created_at
                task_info.last_run_time = job.previous_run_time
                task_info.run_count = job.run_count

                restored_count += 1
            except Exception as e:
                logger.error(
                    f"恢复任务 {job.job_id} 失败",
                    _LOG_COMMAND,
                    e=e,
                )

        if executed_count > 0:
            logger.info(
                f"已执行 {executed_count} 个过期的一次性任务",
                _LOG_COMMAND,
            )
        if restored_count > 0:
            logger.info(
                f"从数据库恢复 {restored_count} 个定时任务",
                _LOG_COMMAND,
            )
        if deleted_count > 0:
            logger.debug(
                f"已清理 {deleted_count} 个无效任务",
                _LOG_COMMAND,
            )
        return restored_count
