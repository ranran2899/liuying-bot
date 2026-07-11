"""数据库监控模块

提供连接池监控和泄漏检测功能，合并连接池指标收集、告警回调与
连接泄漏检测为一体。

核心组件:
    - ``PoolMonitor``: 连接池监控器，收集指标、触发告警
    - ``ConnectionLeakDetector``: 连接泄漏检测器
    - ``pool_monitor``: 连接池监控器单例
    - ``leak_detector``: 泄漏检测器单例
"""

import asyncio
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
import time
from typing import TYPE_CHECKING

from liuying.utils.log import logger

from .config import LOG_COMMAND

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


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


async def _stop_monitor_task(task: asyncio.Task | None) -> None:
    """安全停止监控任务

    参数:
        task: 监控任务
    """
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def _run_monitor_loop(interval: float, callback: Callable[[], None]) -> None:
    """通用监控循环

    参数:
        interval: 检查间隔（秒）
        callback: 每次循环执行的回调
    """
    while True:
        await asyncio.sleep(interval)
        callback()


class PoolMonitor:
    """连接池监控器

    收集各数据库连接池指标，按阈值触发告警，并维护指标历史与告警队列。

    属性:
        warning_threshold: 警告阈值（使用率）
        critical_threshold: 严重阈值（使用率）
        check_interval: 检查间隔（秒）
    """

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
            log_func = (
                logger.error
                if alert.level == AlertLevel.CRITICAL
                else logger.warning
            )
            log_func(f"连接池告警 [{alert.level}]: {alert.message}", LOG_COMMAND)
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
            _run_monitor_loop(self.check_interval, self._check_all_pools)
        )
        logger.info("连接池监控已启动", LOG_COMMAND)

    async def stop_monitoring(self) -> None:
        """停止连接池监控"""
        await _stop_monitor_task(self._monitor_task)
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


class ConnectionLeakDetector:
    """连接泄漏检测器

    跟踪会话连接的注册与注销，按阈值检测潜在泄漏并触发回调。

    属性:
        leak_threshold: 连接占用超过此时间视为潜在泄漏（秒）
        check_interval: 检查间隔（秒）
        max_leak_age: 最大泄漏时间（秒）
    """

    __slots__ = (
        "_connections",
        "_leak_callbacks",
        "_monitor_task",
        "check_interval",
        "leak_threshold",
        "max_leak_age",
    )

    def __init__(
        self,
        leak_threshold: float = 30.0,
        check_interval: float = 60.0,
        max_leak_age: float = 300.0,
    ):
        """初始化连接泄漏检测器

        参数:
            leak_threshold: 连接占用超过此时间视为潜在泄漏（秒）
            check_interval: 检查间隔（秒）
            max_leak_age: 最大泄漏时间，超过此时间强制告警（秒）
        """
        self.leak_threshold = leak_threshold
        self.check_interval = check_interval
        self.max_leak_age = max_leak_age
        self._connections: dict[int, tuple[str, float, str]] = {}
        self._monitor_task: asyncio.Task | None = None
        self._leak_callbacks: list[Callable[[str, int, float], None]] = []

    def register_session(
        self, db_name: str, session_id: int, trace_info: str = ""
    ) -> None:
        """注册会话连接

        参数:
            db_name: 数据库名称
            session_id: 会话ID
            trace_info: 追踪信息
        """
        self._connections[session_id] = (db_name, time.time(), trace_info)

    def unregister_session(self, session_id: int) -> None:
        """注销会话连接

        参数:
            session_id: 会话ID
        """
        self._connections.pop(session_id, None)

    def detect_leaks(self) -> list[tuple[str, int, float, str]]:
        """检测泄漏的连接

        返回:
            list: 泄漏连接列表 [(db_name, session_id, 占用时间, 追踪信息)]
        """
        now = time.time()
        return [
            (db_name, sid, now - t, info)
            for sid, (db_name, t, info) in list(self._connections.items())
            if now - t > self.leak_threshold
        ]

    def add_leak_callback(
        self, callback: Callable[[str, int, float], None]
    ) -> None:
        """添加泄漏回调函数

        参数:
            callback: 回调函数，参数为 (db_name, session_id, 占用时间)
        """
        self._leak_callbacks.append(callback)

    def _check_leaks(self):
        """执行泄漏检查并触发回调"""
        for db_name, session_id, age, trace_info in self.detect_leaks():
            logger.warning(
                f"检测到潜在连接泄漏: 数据库={db_name}, "
                f"会话ID={session_id}, 占用时间={age:.1f}秒, 追踪={trace_info}",
                LOG_COMMAND,
            )
            for callback in self._leak_callbacks:
                try:
                    callback(db_name, session_id, age)
                except Exception as e:
                    logger.error(f"泄漏回调执行失败: {e}", LOG_COMMAND)

    async def start_monitoring(self) -> None:
        """启动泄漏监控"""
        if self._monitor_task and not self._monitor_task.done():
            return
        self._monitor_task = asyncio.create_task(
            _run_monitor_loop(self.check_interval, self._check_leaks)
        )
        logger.info("连接泄漏监控已启动", LOG_COMMAND)

    async def stop_monitoring(self) -> None:
        """停止泄漏监控"""
        await _stop_monitor_task(self._monitor_task)
        self._monitor_task = None
        logger.info("连接泄漏监控已停止", LOG_COMMAND)

    def get_stats(self) -> dict:
        """获取泄漏检测统计信息

        返回:
            dict: 统计信息
        """
        now = time.time()
        ages = [now - t for _, t, _ in self._connections.values()]
        return {
            "active_connections": len(self._connections),
            "potential_leaks": len(self.detect_leaks()),
            "avg_connection_age": sum(ages) / len(ages) if ages else 0,
            "max_connection_age": max(ages) if ages else 0,
            "leak_threshold": self.leak_threshold,
        }


pool_monitor = PoolMonitor()
"""连接池监控器单例"""

leak_detector = ConnectionLeakDetector()
"""连接泄漏检测器单例"""
