from contextlib import suppress
from datetime import datetime
import time
from typing import ClassVar
import uuid

from liuying.configs.config import Config
from liuying.models._log.scheduler_log import SchedulerLog
from liuying.utils.apscheduler import (
    TaskEvent,
    TaskEventType,
    event_bus,
    metrics_collector,
)
from liuying.utils.log import logger

Config.add_plugin_config(
    "hook",
    "SCHEDULER_MONITOR_ENABLE",
    True,
    help="是否启用定时任务监控",
    default_value=True,
    type=bool,
)

Config.add_plugin_config(
    "hook",
    "SCHEDULER_LOG_TO_DB",
    True,
    help="是否记录定时任务日志到数据库",
    default_value=True,
    type=bool,
)

LOG_COMMAND = "SchedulerHook"


class SchedulerMonitor:
    """定时任务监控器

    使用项目本地的 event_bus 订阅任务事件，
    提供日志记录和状态监控功能。
    """

    _running_tasks: ClassVar[dict[str, float]] = {}

    @classmethod
    async def on_task_started(cls, event: TaskEvent):
        """任务开始执行

        参数:
            event: 任务事件
        """
        cls._running_tasks[event.task_id] = time.time()
        logger.debug(
            f"任务开始执行: {event.task_name}({event.task_id})",
            LOG_COMMAND,
        )

    @classmethod
    async def on_task_finished(cls, event: TaskEvent):
        """任务执行完成

        参数:
            event: 任务事件
        """
        start_time = cls._running_tasks.pop(event.task_id, None)
        duration = time.time() - start_time if start_time else 0

        logger.debug(
            f"任务执行完成: {event.task_name}({event.task_id}), "
            f"耗时: {duration:.3f}s",
            LOG_COMMAND,
        )

        if Config.get_config("hook", "SCHEDULER_LOG_TO_DB"):
            duration = event.data.get("duration", duration)
            await cls._save_log(
                job_id=event.task_id,
                job_name=event.task_name,
                trigger_type=event.trigger_type,
                group=event.group,
                success=True,
                duration=duration,
            )

    @classmethod
    async def on_task_failed(cls, event: TaskEvent):
        """任务执行失败

        参数:
            event: 任务事件
        """
        start_time = cls._running_tasks.pop(event.task_id, None)
        duration = time.time() - start_time if start_time else 0

        error = event.data.get("error", "未知错误")

        logger.error(
            f"任务执行失败: {event.task_name}({event.task_id}), "
            f"错误: {error}, 耗时: {duration:.3f}s",
            LOG_COMMAND,
        )

        if Config.get_config("hook", "SCHEDULER_LOG_TO_DB"):
            duration = event.data.get("duration", duration)
            await cls._save_log(
                job_id=event.task_id,
                job_name=event.task_name,
                trigger_type=event.trigger_type,
                group=event.group,
                success=False,
                duration=duration,
                error_message=error,
            )

    @classmethod
    async def on_task_missed(cls, event: TaskEvent):
        """任务错过执行

        参数:
            event: 任务事件
        """
        logger.warning(
            f"任务错过执行: {event.task_name}({event.task_id})",
            LOG_COMMAND,
        )

    @classmethod
    async def on_task_timeout(cls, event: TaskEvent):
        """任务执行超时

        参数:
            event: 任务事件
        """
        logger.warning(
            f"任务执行超时: {event.task_name}({event.task_id})",
            LOG_COMMAND,
        )

    @classmethod
    async def on_alert_triggered(cls, event: TaskEvent):
        """告警触发

        参数:
            event: 任务事件
        """
        alert = event.data.get("alert")
        if alert:
            logger.warning(
                f"定时任务告警: {event.task_name}({event.task_id}), "
                f"类型: {alert.alert_type.name}, 消息: {alert.message}",
                LOG_COMMAND,
            )

    @classmethod
    async def _save_log(
        cls,
        job_id: str,
        job_name: str | None,
        trigger_type: str | None,
        group: str | None,
        success: bool,
        duration: float,
        error_message: str | None = None,
    ):
        """保存日志到数据库

        参数:
            job_id: 任务ID
            job_name: 任务名称
            trigger_type: 触发器类型
            group: 分组
            success: 是否成功
            duration: 执行时长
            error_message: 错误信息
        """
        with suppress(Exception):
            await SchedulerLog.create_log(
                log_id=str(uuid.uuid4()),
                job_id=job_id,
                job_name=job_name or job_id,
                trigger_type=trigger_type,
                group=group or "default",
                start_time=datetime.now(),
                end_time=datetime.now(),
                duration=duration,
                success=success,
                error_message=error_message,
            )

    @classmethod
    def get_stats(cls) -> dict:
        """获取统计数据

        返回:
            dict: 统计数据
        """
        metrics = metrics_collector.get_all_metrics()
        return {
            "scheduler": metrics.get("scheduler", {}),
            "tasks_count": len(metrics.get("tasks", [])),
            "groups_count": len(metrics.get("groups", [])),
            "running_tasks": len(cls._running_tasks),
        }


def setup_scheduler_hooks():
    """设置调度器钩子"""
    if not Config.get_config("hook", "SCHEDULER_MONITOR_ENABLE"):
        return

    event_bus.subscribe(TaskEventType.TASK_STARTED, SchedulerMonitor.on_task_started)
    event_bus.subscribe(TaskEventType.TASK_FINISHED, SchedulerMonitor.on_task_finished)
    event_bus.subscribe(TaskEventType.TASK_FAILED, SchedulerMonitor.on_task_failed)
    event_bus.subscribe(TaskEventType.TASK_MISSED, SchedulerMonitor.on_task_missed)
    event_bus.subscribe(TaskEventType.TASK_TIMEOUT, SchedulerMonitor.on_task_timeout)
    event_bus.subscribe(
        TaskEventType.ALERT_TRIGGERED,
        SchedulerMonitor.on_alert_triggered
        )

    logger.info("定时任务监控 Hook 已启用", LOG_COMMAND)


setup_scheduler_hooks()
