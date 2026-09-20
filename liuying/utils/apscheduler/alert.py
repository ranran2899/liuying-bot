"""
定时任务告警系统

提供任务失败率、连续失败、超时等场景的告警功能，
通过事件总线发布 ALERT_TRIGGERED 事件，由外部订阅者消费。
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
import uuid

from liuying.utils.log import logger

from .constants import (
    DEFAULT_ALERT_CHECK_INTERVAL,
    DEFAULT_ALERT_CONSECUTIVE_FAILURES,
    DEFAULT_ALERT_COOLDOWN,
    DEFAULT_ALERT_FAILURE_RATE_THRESHOLD,
    DEFAULT_ALERT_LONG_RUNNING_THRESHOLD,
    DEFAULT_ALERT_MIN_TOTAL_EXECUTIONS,
    DEFAULT_ALERT_QUEUE_THRESHOLD,
    DEFAULT_ALERT_TIMEOUT_THRESHOLD,
)
from .events import TaskEvent, TaskEventType, event_bus
from .metrics import MetricsCollector, metrics_collector

_LOG_COMMAND = "SchedulerAlert"


class AlertType(StrEnum):
    """告警类型"""

    HIGH_FAILURE_RATE = "high_failure_rate"
    """高失败率"""
    CONSECUTIVE_FAILURES = "consecutive_failures"
    """连续失败"""
    TASK_TIMEOUT = "task_timeout"
    """任务超时"""
    LONG_RUNNING = "long_running"
    """长时间运行"""
    MISSED_EXECUTIONS = "missed_executions"
    """错过执行"""
    QUEUE_BACKLOG = "queue_backlog"
    """队列积压"""


@dataclass(slots=True)
class AlertConfig:
    """告警配置"""

    enabled: bool = True
    """是否启用"""
    failure_rate_threshold: float = DEFAULT_ALERT_FAILURE_RATE_THRESHOLD
    """失败率阈值(0-1)"""
    consecutive_failures_threshold: int = DEFAULT_ALERT_CONSECUTIVE_FAILURES
    """连续失败阈值"""
    timeout_threshold_seconds: float = DEFAULT_ALERT_TIMEOUT_THRESHOLD
    """超时阈值(秒)"""
    long_running_threshold_seconds: float = DEFAULT_ALERT_LONG_RUNNING_THRESHOLD
    """长时间运行阈值(秒)"""
    queue_backlog_threshold: int = DEFAULT_ALERT_QUEUE_THRESHOLD
    """队列积压阈值"""
    check_interval_seconds: float = DEFAULT_ALERT_CHECK_INTERVAL
    """检查间隔(秒)"""
    cooldown_seconds: float = DEFAULT_ALERT_COOLDOWN
    """告警冷却时间(秒)"""
    min_total_executions: int = DEFAULT_ALERT_MIN_TOTAL_EXECUTIONS
    """失败率告警的最小执行次数门槛"""
    alert_task_ids: list[str] = field(default_factory=list)
    """需要告警的任务ID列表，空列表表示所有任务"""
    alert_groups: list[str] = field(default_factory=list)
    """需要告警的分组列表，空列表表示所有分组"""


@dataclass(slots=True)
class Alert:
    """告警（作为 ALERT_TRIGGERED 事件的 data 载荷）"""

    alert_id: str
    """告警ID"""
    alert_type: AlertType
    """告警类型"""
    task_id: str | None = None
    """任务ID"""
    task_name: str | None = None
    """任务名称"""
    group: str | None = None
    """分组名称"""
    message: str = ""
    """告警消息"""
    timestamp: datetime = field(default_factory=datetime.now)
    """告警时间"""
    data: dict[str, Any] = field(default_factory=dict)
    """附加数据"""


class AlertManager:
    """告警管理器"""

    def __init__(
        self,
        config: AlertConfig | None = None,
        metrics: MetricsCollector | None = None,
    ) -> None:
        self.config = config or AlertConfig()
        self.metrics = metrics or metrics_collector
        self._last_alert_time: dict[str, datetime] = {}
        self._check_task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """启动告警检查"""
        if self._running:
            return
        self._running = True
        self._check_task = asyncio.create_task(self._check_loop())
        logger.info("告警管理器已启动", _LOG_COMMAND)

    async def stop(self) -> None:
        """停止告警检查"""
        self._running = False
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
        logger.info("告警管理器已停止", _LOG_COMMAND)

    async def _check_loop(self) -> None:
        """检查循环"""
        while self._running:
            try:
                await self._check_all_tasks()
                await self._check_queue()
            except Exception as e:
                logger.error("告警检查失败", _LOG_COMMAND, e=e)
            await asyncio.sleep(self.config.check_interval_seconds)

    async def _check_all_tasks(self) -> None:
        """检查所有任务"""
        if not self.config.enabled:
            return

        for task_metrics in self.metrics.get_all_task_metrics():
            if not self._should_alert_task(task_metrics.task_id, task_metrics.group):
                continue

            # 检查连续失败
            if (
                task_metrics.consecutive_failures
                >= self.config.consecutive_failures_threshold
            ):
                await self._trigger_alert(
                    AlertType.CONSECUTIVE_FAILURES,
                    task_id=task_metrics.task_id,
                    task_name=task_metrics.task_name,
                    group=task_metrics.group,
                    message=f"任务连续失败 {task_metrics.consecutive_failures} 次",
                    data={
                        "consecutive_failures": task_metrics.consecutive_failures,
                        "threshold": self.config.consecutive_failures_threshold,
                    },
                )

            # 检查失败率
            failure_rate = 1 - task_metrics.success_rate
            if (
                task_metrics.total_executions > self.config.min_total_executions
                and failure_rate >= self.config.failure_rate_threshold
            ):
                await self._trigger_alert(
                    AlertType.HIGH_FAILURE_RATE,
                    task_id=task_metrics.task_id,
                    task_name=task_metrics.task_name,
                    group=task_metrics.group,
                    message=f"任务失败率过高: {failure_rate:.1%}",
                    data={
                        "failure_rate": failure_rate,
                        "threshold": self.config.failure_rate_threshold,
                        "total_executions": task_metrics.total_executions,
                    },
                )

    async def _check_queue(self) -> None:
        """检查队列"""
        if not self.config.enabled:
            return

        scheduler_metrics = self.metrics.get_scheduler_metrics()
        if scheduler_metrics.queue_size >= self.config.queue_backlog_threshold:
            await self._trigger_alert(
                AlertType.QUEUE_BACKLOG,
                message=f"队列积压严重: {scheduler_metrics.queue_size}",
                data={
                    "queue_size": scheduler_metrics.queue_size,
                    "threshold": self.config.queue_backlog_threshold,
                },
            )

    async def _check_duration_threshold(
        self,
        alert_type: AlertType,
        task_id: str,
        task_name: str,
        group: str,
        duration: float,
        threshold: float,
        message_template: str,
    ) -> None:
        """
        通用时长阈值检查（被 check_timeout/check_long_running 复用）

        参数:
            alert_type: 告警类型
            task_id: 任务ID
            task_name: 任务名称
            group: 分组名称
            duration: 执行耗时
            threshold: 阈值
            message_template: 消息模板
        """
        if not self.config.enabled:
            return
        if not self._should_alert_task(task_id, group):
            return
        if duration < threshold:
            return
        await self._trigger_alert(
            alert_type,
            task_id=task_id,
            task_name=task_name,
            group=group,
            message=message_template.format(duration=duration),
            data={"duration": duration, "threshold": threshold},
        )

    async def check_timeout(
        self,
        task_id: str,
        task_name: str,
        group: str,
        duration: float,
    ) -> None:
        """
        检查超时

        参数:
            task_id: 任务ID
            task_name: 任务名称
            group: 分组名称
            duration: 执行耗时
        """
        await self._check_duration_threshold(
            AlertType.TASK_TIMEOUT,
            task_id,
            task_name,
            group,
            duration,
            self.config.timeout_threshold_seconds,
            "任务执行超时: {duration:.1f}秒",
        )

    async def check_long_running(
        self,
        task_id: str,
        task_name: str,
        group: str,
        duration: float,
    ) -> None:
        """
        检查长时间运行

        参数:
            task_id: 任务ID
            task_name: 任务名称
            group: 分组名称
            duration: 执行耗时
        """
        await self._check_duration_threshold(
            AlertType.LONG_RUNNING,
            task_id,
            task_name,
            group,
            duration,
            self.config.long_running_threshold_seconds,
            "任务运行时间过长: {duration:.1f}秒",
        )

    async def check_missed(
        self,
        task_id: str,
        task_name: str,
        group: str,
        count: int = 1,
    ) -> None:
        """
        检查错过执行

        参数:
            task_id: 任务ID
            task_name: 任务名称
            group: 分组名称
            count: 错过次数
        """
        if not self.config.enabled:
            return
        if not self._should_alert_task(task_id, group):
            return
        await self._trigger_alert(
            AlertType.MISSED_EXECUTIONS,
            task_id=task_id,
            task_name=task_name,
            group=group,
            message=f"任务错过执行 {count} 次",
            data={"missed_count": count},
        )

    def _should_alert_task(self, task_id: str, group: str) -> bool:
        """
        判断是否应该告警该任务

        参数:
            task_id: 任务ID
            group: 分组名称

        返回:
            是否应该告警
        """
        if self.config.alert_task_ids and task_id not in self.config.alert_task_ids:
            return False
        if self.config.alert_groups and group not in self.config.alert_groups:
            return False
        return True

    async def _trigger_alert(
        self,
        alert_type: AlertType,
        task_id: str | None = None,
        task_name: str | None = None,
        group: str | None = None,
        message: str = "",
        data: dict[str, Any] | None = None,
    ) -> None:
        """
        触发告警（冷却期内静默，发布 ALERT_TRIGGERED 事件）

        参数:
            alert_type: 告警类型
            task_id: 任务ID
            task_name: 任务名称
            group: 分组名称
            message: 告警消息
            data: 附加数据
        """
        alert_key = f"{alert_type.value}_{task_id or 'global'}"

        # 检查冷却时间
        now = datetime.now()
        last_time = self._last_alert_time.get(alert_key)
        if last_time and (
            now - last_time
        ).total_seconds() < self.config.cooldown_seconds:
            return

        alert = Alert(
            alert_id=uuid.uuid4().hex,
            alert_type=alert_type,
            task_id=task_id,
            task_name=task_name,
            group=group,
            message=message,
            data=data or {},
        )
        self._last_alert_time[alert_key] = now

        await event_bus.emit(
            TaskEvent(
                event_type=TaskEventType.ALERT_TRIGGERED,
                task_id=task_id,
                task_name=task_name,
                group=group,
                data={"alert": alert},
            )
        )

        logger.warning(
            f"告警触发: {alert_type.name} - {message}",
            _LOG_COMMAND,
        )


# 全局告警管理器实例
alert_manager = AlertManager()
