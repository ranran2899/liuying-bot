"""连接池监控器"""

import asyncio
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
import time
from typing import TYPE_CHECKING

from liuying.utils.log import logger

from ..config import LOG_COMMAND

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

from ._utils import run_monitor_loop, stop_monitor_task


class AlertLevel(StrEnum):
    """告警级别"""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(slots=True)
class PoolAlert:
    """连接池告警信息"""

    db_name: str
    level: AlertLevel
    message: str
    usage_rate: float
    timestamp: float = field(default_factory=time.time)


@dataclass(slots=True)
class PoolMetrics:
    """连接池指标"""

    db_name: str
    pool_size: int
    checked_in: int
    checked_out: int
    overflow: int
    usage_rate: float
    is_healthy: bool
    timestamp: float = field(default_factory=time.time)


class PoolMonitor:
    """连接池监控器"""

    __slots__ = (
        "_alert_callbacks",
        "_alerts",
        "_engines",
        "_metrics_history",
        "_monitor_task",
        "check_interval",
        "critical_threshold",
        "warning_threshold",
    )

    def __init__(
        self,
        warning_threshold: float = 0.7,
        critical_threshold: float = 0.9,
        check_interval: float = 30.0,
    ):
        """初始化连接池监控器

        参数:
            warning_threshold: 警告阈值（使用率）
            critical_threshold: 严重阈值（使用率）
            check_interval: 检查间隔（秒）
        """
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.check_interval = check_interval
        self._engines: dict[str, "AsyncEngine"] = {}
        self._metrics_history: dict[str, deque[PoolMetrics]] = {}
        self._alerts: deque[PoolAlert] = deque(maxlen=100)
        self._alert_callbacks: list[Callable[[PoolAlert], None]] = []
        self._monitor_task: asyncio.Task | None = None

    def register_engine(self, db_name: str, engine: "AsyncEngine") -> None:
        """注册数据库引擎

        参数:
            db_name: 数据库名称
            engine: 异步引擎
        """
        self._engines[db_name] = engine
        self._metrics_history[db_name] = deque(maxlen=100)

    def unregister_engine(self, db_name: str) -> None:
        """注销数据库引擎

        参数:
            db_name: 数据库名称
        """
        self._engines.pop(db_name, None)
        self._metrics_history.pop(db_name, None)

    def collect_metrics(self, db_name: str) -> PoolMetrics | None:
        """收集连接池指标

        参数:
            db_name: 数据库名称

        返回:
            PoolMetrics | None: 连接池指标
        """
        if db_name not in self._engines:
            return None

        pool = self._engines[db_name].pool
        pool_size = pool.size()
        checked_out = pool.checkedout()
        usage_rate = checked_out / pool_size if pool_size > 0 else 0

        metrics = PoolMetrics(
            db_name=db_name,
            pool_size=pool_size,
            checked_in=pool.checkedin(),
            checked_out=checked_out,
            overflow=pool.overflow(),
            usage_rate=usage_rate,
            is_healthy=usage_rate < self.critical_threshold,
        )
        self._metrics_history[db_name].append(metrics)
        return metrics

    def check_alerts(self, metrics: PoolMetrics) -> PoolAlert | None:
        """检查是否需要告警

        参数:
            metrics: 连接池指标

        返回:
            PoolAlert | None: 告警信息
        """
        match metrics.usage_rate:
            case rate if rate >= self.critical_threshold:
                level, msg = AlertLevel.CRITICAL, f"连接池使用率严重过高: {rate:.1%}"
            case rate if rate >= self.warning_threshold:
                level, msg = AlertLevel.WARNING, f"连接池使用率过高: {rate:.1%}"
            case _:
                return None

        alert = PoolAlert(
            db_name=metrics.db_name,
            level=level,
            message=msg,
            usage_rate=metrics.usage_rate,
        )
        self._alerts.append(alert)
        return alert

    def add_alert_callback(self, callback: Callable[[PoolAlert], None]) -> None:
        """添加告警回调函数

        参数:
            callback: 回调函数
        """
        self._alert_callbacks.append(callback)

    def _check_all_pools(self):
        """检查所有连接池状态"""
        for db_name in list(self._engines.keys()):
            metrics = self.collect_metrics(db_name)
            if not metrics:
                continue
            alert = self.check_alerts(metrics)
            if not alert:
                continue
            is_critical = alert.level == AlertLevel.CRITICAL
            log_func = logger.error if is_critical else logger.warning
            log_func(
                f"连接池告警 [{alert.level}]: {alert.message}",
                LOG_COMMAND,
            )
            for callback in self._alert_callbacks:
                try:
                    callback(alert)
                except Exception as e:
                    logger.error(f"告警回调执行失败: {e}", LOG_COMMAND)

    async def start_monitoring(self) -> None:
        """启动连接池监控"""
        if self._monitor_task and not self._monitor_task.done():
            return
        self._monitor_task = asyncio.create_task(
            run_monitor_loop(self.check_interval, self._check_all_pools)
        )
        logger.info("连接池监控已启动", LOG_COMMAND)

    async def stop_monitoring(self) -> None:
        """停止连接池监控"""
        await stop_monitor_task(self._monitor_task)
        self._monitor_task = None
        logger.info("连接池监控已停止", LOG_COMMAND)

    def get_metrics_history(self, db_name: str) -> list[PoolMetrics]:
        """获取指标历史

        参数:
            db_name: 数据库名称

        返回:
            list[PoolMetrics]: 指标历史列表
        """
        return list(self._metrics_history.get(db_name, []))

    def get_recent_alerts(self, count: int = 10) -> list[PoolAlert]:
        """获取最近的告警

        参数:
            count: 获取数量

        返回:
            list[PoolAlert]: 告警列表
        """
        return list(self._alerts)[-count:] if self._alerts else []

    def get_health_score(self, db_name: str) -> dict:
        """获取健康评分

        参数:
            db_name: 数据库名称

        返回:
            dict: 健康评分信息
        """
        history = self._metrics_history.get(db_name)
        if not history:
            return {"score": 0, "status": "unknown", "message": "无历史数据"}

        recent = list(history)[-10:]
        avg_usage = sum(m.usage_rate for m in recent) / len(recent)
        max_usage = max(m.usage_rate for m in recent)

        match avg_usage:
            case r if r < 0.5:
                score, status, message = 100, "healthy", "连接池状态良好"
            case r if r < 0.7:
                score, status, message = 80, "normal", "连接池状态正常"
            case r if r < 0.9:
                score, status, message = 60, "warning", "连接池压力较大"
            case _:
                score, status, message = 30, "critical", "连接池压力过大"

        return {
            "score": score,
            "status": status,
            "message": message,
            "avg_usage": avg_usage,
            "max_usage": max_usage,
        }


pool_monitor = PoolMonitor()
