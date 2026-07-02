"""
定时任务告警系统
提供任务失败率、连续失败等场景的告警功能
"""

import asyncio
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
import uuid

from liuying.utils.log import logger

from .events import TaskEvent, TaskEventType, event_bus
from .metrics import MetricsCollector, metrics_collector


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
    failure_rate_threshold: float = 0.3
    """失败率阈值(0-1)"""
    failure_rate_window_minutes: int = 60
    """失败率统计窗口(分钟)"""
    consecutive_failures_threshold: int = 5
    """连续失败阈值"""
    timeout_threshold_seconds: float = 300.0
    """超时阈值(秒)"""
    long_running_threshold_seconds: float = 600.0
    """长时间运行阈值(秒)"""
    queue_backlog_threshold: int = 100
    """队列积压阈值"""
    check_interval_seconds: float = 60.0
    """检查间隔(秒)"""
    cooldown_seconds: float = 300.0
    """告警冷却时间(秒)"""
    alert_task_ids: list[str] = field(default_factory=list)
    """需要告警的任务ID列表，空列表表示所有任务"""
    alert_groups: list[str] = field(default_factory=list)
    """需要告警的分组列表，空列表表示所有分组"""


@dataclass(slots=True)
class Alert:
    """告警"""

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
    acknowledged: bool = False
    """是否已确认"""
    acknowledged_at: datetime | None = None
    """确认时间"""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "alert_id": self.alert_id,
            "alert_type": self.alert_type.name,
            "task_id": self.task_id,
            "task_name": self.task_name,
            "group": self.group,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "acknowledged": self.acknowledged,
            "acknowledged_at": (
                self.acknowledged_at.isoformat()
                if self.acknowledged_at else None
            ),
        }


class AlertManager:
    """告警管理器"""

    def __init__(
        self,
        config: AlertConfig | None = None,
        metrics: MetricsCollector | None = None,
    ) -> None:
        self.config = config or AlertConfig()
        self.metrics = metrics or metrics_collector
        self._alerts: deque[Alert] = deque(maxlen=1000)
        self._last_alert_time: dict[str, datetime] = {}
        self._alert_handlers: list[Callable[[Alert], Any]] = []
        self._check_task: asyncio.Task | None = None
        self._running = False

    def add_alert_handler(self, handler: Callable[[Alert], Any]) -> None:
        """
        添加告警处理器

        参数:
            handler: 告警处理函数
        """
        self._alert_handlers.append(handler)

    def remove_alert_handler(self, handler: Callable[[Alert], Any]) -> None:
        """
        移除告警处理器

        参数:
            handler: 告警处理函数
        """
        if handler in self._alert_handlers:
            self._alert_handlers.remove(handler)

    async def start(self) -> None:
        """启动告警检查"""
        if self._running:
            return
        self._running = True
        self._check_task = asyncio.create_task(self._check_loop())
        logger.info("告警管理器已启动")

    async def stop(self) -> None:
        """停止告警检查"""
        self._running = False
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
        logger.info("告警管理器已停止")

    async def _check_loop(self) -> None:
        """检查循环"""
        while self._running:
            try:
                await self._check_all_tasks()
                await self._check_queue()
            except Exception as e:
                logger.error("告警检查失败", e=e)
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
            if (
                task_metrics.total_executions > 10
                and task_metrics.success_rate < (1 - self.config.failure_rate_threshold)
            ):
                await self._trigger_alert(
                    AlertType.HIGH_FAILURE_RATE,
                    task_id=task_metrics.task_id,
                    task_name=task_metrics.task_name,
                    group=task_metrics.group,
                    message=f"任务失败率过高: {task_metrics.success_rate:.1%}",
                    data={
                        "success_rate": task_metrics.success_rate,
                        "threshold": 1 - self.config.failure_rate_threshold,
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
        if not self.config.enabled:
            return

        if not self._should_alert_task(task_id, group):
            return

        if duration >= self.config.timeout_threshold_seconds:
            await self._trigger_alert(
                AlertType.TASK_TIMEOUT,
                task_id=task_id,
                task_name=task_name,
                group=group,
                message=f"任务执行超时: {duration:.1f}秒",
                data={
                    "duration": duration,
                    "threshold": self.config.timeout_threshold_seconds,
                },
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
        if not self.config.enabled:
            return

        if not self._should_alert_task(task_id, group):
            return

        if duration >= self.config.long_running_threshold_seconds:
            await self._trigger_alert(
                AlertType.LONG_RUNNING,
                task_id=task_id,
                task_name=task_name,
                group=group,
                message=f"任务运行时间过长: {duration:.1f}秒",
                data={
                    "duration": duration,
                    "threshold": self.config.long_running_threshold_seconds,
                },
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
        触发告警

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
        if alert_key in self._last_alert_time:
            last_time = self._last_alert_time[alert_key]
            if (now - last_time).total_seconds() < self.config.cooldown_seconds:
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

        # deque(maxlen=1000) 自动淘汰旧记录，无需手动截断
        self._alerts.append(alert)
        self._last_alert_time[alert_key] = now

        # 发布告警事件
        await event_bus.emit(
            TaskEvent(
                event_type=TaskEventType.ALERT_TRIGGERED,
                task_id=task_id,
                task_name=task_name,
                group=group,
                data={"alert": alert},
            )
        )

        # 调用告警处理器
        for handler in self._alert_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(alert)
                else:
                    handler(alert)
            except Exception as e:
                logger.error(f"告警处理器执行失败: {handler.__name__}", e=e)

        logger.warning(f"告警触发: {alert_type.name} - {message}")

    def get_alerts(
        self,
        alert_type: AlertType | None = None,
        acknowledged: bool | None = None,
        limit: int = 100,
    ) -> list[Alert]:
        """
        获取告警列表

        参数:
            alert_type: 告警类型过滤
            acknowledged: 确认状态过滤
            limit: 返回数量限制

        返回:
            告警列表
        """
        alerts = list(self._alerts)
        if alert_type:
            alerts = [a for a in alerts if a.alert_type == alert_type]
        if acknowledged is not None:
            alerts = [a for a in alerts if a.acknowledged == acknowledged]
        return alerts[-limit:]

    async def acknowledge_alert(self, alert_id: str) -> bool:
        """
        确认告警

        参数:
            alert_id: 告警ID

        返回:
            是否成功
        """
        for alert in self._alerts:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                alert.acknowledged_at = datetime.now()
                return True
        return False

    def get_unacknowledged_count(self) -> int:
        """
        获取未确认告警数量

        返回:
            未确认告警数量
        """
        return sum(1 for a in self._alerts if not a.acknowledged)


# 全局告警管理器实例
alert_manager = AlertManager()
