"""
定时任务监控和指标系统
提供任务执行的统计和监控功能
"""

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class TaskMetrics:
    """任务指标"""

    task_id: str
    """任务ID"""
    task_name: str
    """任务名称"""
    group: str = "default"
    """分组名称"""
    total_executions: int = 0
    """总执行次数"""
    success_count: int = 0
    """成功次数"""
    fail_count: int = 0
    """失败次数"""
    timeout_count: int = 0
    """超时次数"""
    total_duration: float = 0.0
    """总执行耗时"""
    min_duration: float = float("inf")
    """最小执行耗时"""
    max_duration: float = 0.0
    """最大执行耗时"""
    last_execution_time: datetime | None = None
    """最后执行时间"""
    last_success_time: datetime | None = None
    """最后成功时间"""
    last_fail_time: datetime | None = None
    """最后失败时间"""
    consecutive_failures: int = 0
    """连续失败次数"""
    _executions_by_minute: OrderedDict = field(default_factory=OrderedDict)
    """每分钟执行次数（使用 OrderedDict 维护时间顺序）"""
    retry_count: int = 0
    """总重试次数"""
    _max_minute_records: int = 60
    """最大保留分钟记录数"""

    @property
    def executions_by_minute(self) -> dict[str, int]:
        """
        获取每分钟执行次数（兼容旧接口）

        返回:
            时间字符串到执行次数的映射
        """
        return dict(self._executions_by_minute)

    def get_recent_executions(self, minutes: int = 10) -> dict[str, int]:
        """
        获取最近 N 分钟的执行次数

        参数:
            minutes: 要获取的分钟数

        返回:
            时间字符串到执行次数的映射（按时间倒序）
        """
        items = list(self._executions_by_minute.items())[-minutes:]
        return dict(reversed(items))

    def get_executions_in_range(
        self, start: datetime, end: datetime
    ) -> dict[str, int]:
        """
        获取指定时间范围内的执行次数

        参数:
            start: 开始时间
            end: 结束时间

        返回:
            时间字符串到执行次数的映射
        """
        result = {}
        for key, count in self._executions_by_minute.items():
            try:
                key_time = datetime.strptime(key, "%Y-%m-%d %H:%M")
                if start <= key_time <= end:
                    result[key] = count
            except ValueError:
                continue
        return result

    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_executions == 0:
            return 0.0
        return self.success_count / self.total_executions

    @property
    def avg_duration(self) -> float:
        """平均执行耗时"""
        if self.total_executions == 0:
            return 0.0
        return self.total_duration / self.total_executions

    def record_execution(
        self,
        success: bool,
        duration: float,
        timeout: bool = False,
        retry: bool = False,
    ) -> None:
        """
        记录执行结果

        参数:
            success: 是否成功
            duration: 执行耗时(秒)
            timeout: 是否超时
            retry: 是否为重试
        """
        now = datetime.now()

        self.total_executions += 1
        self.last_execution_time = now
        self.total_duration += duration

        if duration < self.min_duration:
            self.min_duration = duration
        if duration > self.max_duration:
            self.max_duration = duration

        minute_key = now.strftime("%Y-%m-%d %H:%M")
        self._executions_by_minute[minute_key] = (
            self._executions_by_minute.get(minute_key, 0) + 1
        )
        while len(self._executions_by_minute) > self._max_minute_records:
            self._executions_by_minute.popitem(last=False)

        if success:
            self.success_count += 1
            self.last_success_time = now
            self.consecutive_failures = 0
        else:
            self.fail_count += 1
            self.last_fail_time = now
            self.consecutive_failures += 1

        if timeout:
            self.timeout_count += 1
        if retry:
            self.retry_count += 1

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "group": self.group,
            "total_executions": self.total_executions,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "timeout_count": self.timeout_count,
            "success_rate": self.success_rate,
            "avg_duration": self.avg_duration,
            "min_duration": (
                self.min_duration if self.min_duration != float("inf") else 0
            ),
            "max_duration": self.max_duration,
            "last_execution_time": (
                self.last_execution_time.isoformat()
                if self.last_execution_time else None
            ),
            "last_success_time": (
                self.last_success_time.isoformat()
                if self.last_success_time else None
            ),
            "last_fail_time": (
                self.last_fail_time.isoformat()
                if self.last_fail_time else None
            ),
            "consecutive_failures": self.consecutive_failures,
            "retry_count": self.retry_count,
        }


@dataclass(slots=True)
class SchedulerMetrics:
    """调度器指标"""

    start_time: datetime = field(default_factory=datetime.now)
    """启动时间"""
    total_tasks: int = 0
    """总任务数"""
    running_tasks: int = 0
    """正在运行的任务数"""
    paused_tasks: int = 0
    """已暂停的任务数"""
    queue_size: int = 0
    """队列大小"""
    total_events_emitted: int = 0
    """总发布事件数"""
    uptime_seconds: float = 0.0
    """运行时长(秒)"""

    def update_uptime(self) -> None:
        """更新运行时长"""
        self.uptime_seconds = (datetime.now() - self.start_time).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        self.update_uptime()
        return {
            "start_time": self.start_time.isoformat(),
            "uptime_seconds": self.uptime_seconds,
            "total_tasks": self.total_tasks,
            "running_tasks": self.running_tasks,
            "paused_tasks": self.paused_tasks,
            "queue_size": self.queue_size,
            "total_events_emitted": self.total_events_emitted,
        }


class MetricsCollector:
    """指标收集器（单线程 asyncio 模型，无需 Lock）"""

    def __init__(self) -> None:
        self._task_metrics: dict[str, TaskMetrics] = {}
        self._scheduler_metrics = SchedulerMetrics()
        self._group_metrics: dict[str, TaskMetrics] = {}

    def get_task_metrics(self, task_id: str) -> TaskMetrics | None:
        """
        获取任务指标

        参数:
            task_id: 任务ID

        返回:
            任务指标对象
        """
        return self._task_metrics.get(task_id)

    def get_or_create_task_metrics(
        self,
        task_id: str,
        task_name: str,
        group: str = "default",
    ) -> TaskMetrics:
        """
        获取或创建任务指标

        参数:
            task_id: 任务ID
            task_name: 任务名称
            group: 分组名称

        返回:
            任务指标对象
        """
        if task_id not in self._task_metrics:
            self._task_metrics[task_id] = TaskMetrics(
                task_id=task_id,
                task_name=task_name,
                group=group,
            )
        return self._task_metrics[task_id]

    def record_task_execution(
        self,
        task_id: str,
        task_name: str,
        group: str,
        success: bool,
        duration: float,
        timeout: bool = False,
        retry: bool = False,
    ) -> None:
        """
        记录任务执行（单线程 asyncio 模型安全）

        参数:
            task_id: 任务ID
            task_name: 任务名称
            group: 分组名称
            success: 是否成功
            duration: 执行耗时
            timeout: 是否超时
            retry: 是否为重试
        """
        metrics = self.get_or_create_task_metrics(task_id, task_name, group)
        metrics.record_execution(success, duration, timeout, retry)

        if group not in self._group_metrics:
            self._group_metrics[group] = TaskMetrics(
                task_id=f"group_{group}",
                task_name=f"分组 {group}",
                group=group,
            )
        self._group_metrics[group].record_execution(
            success, duration, timeout, retry
        )

    def update_scheduler_metrics(
        self,
        total_tasks: int | None = None,
        running_tasks: int | None = None,
        paused_tasks: int | None = None,
        queue_size: int | None = None,
    ) -> None:
        """
        更新调度器指标

        参数:
            total_tasks: 总任务数
            running_tasks: 正在运行的任务数
            paused_tasks: 已暂停的任务数
            queue_size: 队列大小
        """
        if total_tasks is not None:
            self._scheduler_metrics.total_tasks = total_tasks
        if running_tasks is not None:
            self._scheduler_metrics.running_tasks = running_tasks
        if paused_tasks is not None:
            self._scheduler_metrics.paused_tasks = paused_tasks
        if queue_size is not None:
            self._scheduler_metrics.queue_size = queue_size

    def increment_event_count(self) -> None:
        """增加事件计数"""
        self._scheduler_metrics.total_events_emitted += 1

    def get_all_task_metrics(self) -> list[TaskMetrics]:
        """
        获取所有任务指标

        返回:
            任务指标列表
        """
        return list(self._task_metrics.values())

    def get_group_metrics(self, group: str) -> TaskMetrics | None:
        """
        获取分组指标

        参数:
            group: 分组名称

        返回:
            分组指标对象
        """
        return self._group_metrics.get(group)

    def get_all_group_metrics(self) -> list[TaskMetrics]:
        """
        获取所有分组指标

        返回:
            分组指标列表
        """
        return list(self._group_metrics.values())

    def get_scheduler_metrics(self) -> SchedulerMetrics:
        """
        获取调度器指标

        返回:
            调度器指标对象
        """
        return self._scheduler_metrics

    def get_all_metrics(self) -> dict[str, Any]:
        """
        获取所有指标

        返回:
            所有指标的字典
        """
        return {
            "scheduler": self._scheduler_metrics.to_dict(),
            "tasks": [m.to_dict() for m in self._task_metrics.values()],
            "groups": [m.to_dict() for m in self._group_metrics.values()],
        }

    def remove_task_metrics(self, task_id: str) -> None:
        """
        移除任务指标

        参数:
            task_id: 任务ID
        """
        if task_id in self._task_metrics:
            del self._task_metrics[task_id]

    def clear_all(self) -> None:
        """清空所有指标"""
        self._task_metrics.clear()
        self._group_metrics.clear()
        self._scheduler_metrics = SchedulerMetrics()


# 全局指标收集器实例
metrics_collector = MetricsCollector()
