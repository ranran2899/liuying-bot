"""
缓存监控和统计

提供缓存操作的监控、统计和报告功能。
支持P50/P95/P99延迟统计和内存使用统计。
所有数据操作使用 threading.Lock 保护，在 asyncio 单线程事件循环下
不会阻塞其他协程，同时保证线程安全。
"""

from collections.abc import Callable
from functools import wraps
from threading import Lock
import time
from typing import Any, ClassVar, Self

from liuying.utils.log import logger

from .config import LOG_COMMAND
from .metrics import CacheMetrics, CacheMonitorData, estimate_object_size

_METRIC_FIELD_MAP: dict[str, str] = {
    "hit": "hits",
    "miss": "misses",
    "set": "sets",
    "delete": "deletes",
    "error": "errors",
}


class CacheMonitor:
    """缓存监控器

    单例模式管理缓存监控数据，所有数据操作使用 threading.Lock 保护。
    在 asyncio 单线程事件循环下，同步锁的获取是即时的，不会阻塞其他协程。
    """

    _instance: ClassVar[Self | None] = None
    _init_lock: ClassVar[Lock] = Lock()

    def __new__(cls) -> Self:
        """单例模式"""
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._data = CacheMonitorData()
                    instance._sync_lock = Lock()
                    cls._instance = instance
        return cls._instance

    @staticmethod
    def _increment(metrics: CacheMetrics, field_name: str) -> None:
        """安全递增指标字段（需在锁内调用）

        参数:
            metrics: 指标对象
            field_name: 字段名
        """
        current = getattr(metrics, field_name, None)
        if isinstance(current, int):
            setattr(metrics, field_name, current + 1)

    def _record_metric_sync(
        self, cache_type: str, metric_field: str, elapsed_time: float = 0.0
    ) -> None:
        """同步记录指标（线程安全）

        参数:
            cache_type: 缓存类型
            metric_field: 指标字段名
            elapsed_time: 耗时（秒）
        """
        with self._sync_lock:
            self._increment(self._data.global_metrics, metric_field)
            self._increment(self._data.type_metrics[cache_type], metric_field)
            if elapsed_time > 0:
                self._update_time(cache_type, elapsed_time)

    def record(
        self,
        cache_type: str,
        operation: str,
        elapsed_time: float = 0.0,
    ) -> None:
        """根据操作类型记录指标

        参数:
            cache_type: 缓存类型
            operation: 操作类型 (hit/miss/set/delete/error)
            elapsed_time: 耗时（秒）
        """
        field = _METRIC_FIELD_MAP.get(operation)
        if field:
            self._record_metric_sync(cache_type, field, elapsed_time)

    def record_hit(self, cache_type: str, elapsed_time: float = 0.0) -> None:
        """记录缓存命中

        参数:
            cache_type: 缓存类型
            elapsed_time: 耗时（秒）
        """
        self._record_metric_sync(cache_type, "hits", elapsed_time)

    def record_miss(self, cache_type: str, elapsed_time: float = 0.0) -> None:
        """记录缓存未命中

        参数:
            cache_type: 缓存类型
            elapsed_time: 耗时（秒）
        """
        self._record_metric_sync(cache_type, "misses", elapsed_time)

    def record_set(self, cache_type: str, elapsed_time: float = 0.0) -> None:
        """记录缓存设置

        参数:
            cache_type: 缓存类型
            elapsed_time: 耗时（秒）
        """
        self._record_metric_sync(cache_type, "sets", elapsed_time)

    def record_delete(self, cache_type: str, elapsed_time: float = 0.0) -> None:
        """记录缓存删除

        参数:
            cache_type: 缓存类型
            elapsed_time: 耗时（秒）
        """
        self._record_metric_sync(cache_type, "deletes", elapsed_time)

    def record_error(self, cache_type: str, elapsed_time: float = 0.0) -> None:
        """记录缓存错误

        参数:
            cache_type: 缓存类型
            elapsed_time: 耗时（秒）
        """
        self._record_metric_sync(cache_type, "errors", elapsed_time)

    @staticmethod
    def _update_metrics_time(metrics: CacheMetrics, elapsed_time: float) -> None:
        """更新单个指标对象的耗时统计

        参数:
            metrics: 指标对象
            elapsed_time: 耗时（秒）
        """
        metrics.total_time += elapsed_time
        total_ops = metrics.total_operations
        metrics.avg_time = metrics.total_time / total_ops if total_ops > 0 else 0.0
        metrics.record_latency(elapsed_time)

    def _update_time(self, cache_type: str, elapsed_time: float) -> None:
        """更新耗时统计（需在锁内调用）

        参数:
            cache_type: 缓存类型
            elapsed_time: 耗时（秒）
        """
        self._update_metrics_time(self._data.type_metrics[cache_type], elapsed_time)
        self._update_metrics_time(self._data.global_metrics, elapsed_time)

    def update_memory_stats(
        self, cache_type: str, entries: int, size_bytes: int
    ) -> None:
        """更新内存统计

        参数:
            cache_type: 缓存类型
            entries: 条目数
            size_bytes: 内存占用（字节）
        """
        with self._sync_lock:
            self._data.type_metrics[cache_type].memory_stats.update(entries, size_bytes)

            total_entries = sum(
                m.memory_stats.total_entries for m in self._data.type_metrics.values()
            )
            total_size = sum(
                m.memory_stats.estimated_size_bytes
                for m in self._data.type_metrics.values()
            )
            self._data.global_metrics.memory_stats.update(total_entries, total_size)

    def estimate_and_update_memory(self, cache_type: str, data: dict[str, Any]) -> int:
        """估算并更新内存统计

        参数:
            cache_type: 缓存类型
            data: 缓存数据字典

        返回:
            int: 估算的内存大小（字节）
        """
        total_size = sum(estimate_object_size(v) for v in data.values())
        self.update_memory_stats(cache_type, len(data), total_size)
        return total_size

    def _resolve_metrics(self, cache_type: str | None) -> CacheMetrics:
        """解析指标对象（需在锁内调用）

        参数:
            cache_type: 缓存类型，为None时返回全局指标

        返回:
            CacheMetrics: 缓存指标
        """
        if cache_type is None:
            return self._data.global_metrics
        return self._data.type_metrics.get(cache_type, CacheMetrics())

    def get_metrics(self, cache_type: str | None = None) -> CacheMetrics:
        """获取指标（线程安全）

        参数:
            cache_type: 缓存类型，为None时返回全局指标

        返回:
            CacheMetrics: 缓存指标
        """
        with self._sync_lock:
            return self._resolve_metrics(cache_type)

    async def get_metrics_async(self, cache_type: str | None = None) -> CacheMetrics:
        """异步获取指标

        参数:
            cache_type: 缓存类型，为None时返回全局指标

        返回:
            CacheMetrics: 缓存指标
        """
        with self._sync_lock:
            return self._resolve_metrics(cache_type)

    def get_all_metrics(self) -> dict[str, CacheMetrics]:
        """获取所有指标（线程安全）

        返回:
            dict[str, CacheMetrics]: 所有缓存类型的指标
        """
        with self._sync_lock:
            return dict(self._data.type_metrics)

    def get_report(self) -> dict[str, Any]:
        """获取监控报告（线程安全）

        返回:
            dict[str, Any]: 监控报告
        """
        with self._sync_lock:
            return self._build_report()

    async def get_report_async(self) -> dict[str, Any]:
        """异步获取监控报告

        返回:
            dict[str, Any]: 监控报告
        """
        with self._sync_lock:
            return self._build_report()

    @staticmethod
    def _build_metrics_dict(metrics: CacheMetrics) -> dict[str, Any]:
        """构建指标字典

        参数:
            metrics: 缓存指标

        返回:
            dict[str, Any]: 指标字典
        """
        latency = metrics.latency_stats
        memory = metrics.memory_stats
        return {
            "hits": metrics.hits,
            "misses": metrics.misses,
            "hit_rate": f"{metrics.hit_rate:.2f}%",
            "sets": metrics.sets,
            "deletes": metrics.deletes,
            "errors": metrics.errors,
            "total_operations": metrics.total_operations,
            "avg_time_ms": round(metrics.avg_time * 1000, 2),
            "latency": {
                "p50_ms": round(latency.p50, 2),
                "p95_ms": round(latency.p95, 2),
                "p99_ms": round(latency.p99, 2),
                "min_ms": round(latency.min, 2),
                "max_ms": round(latency.max, 2),
            },
            "memory": {
                "total_entries": memory.total_entries,
                "estimated_size_mb": round(memory.estimated_size_mb, 2),
                "avg_entry_size_bytes": round(memory.avg_entry_size, 2),
            },
        }

    def _build_report(self) -> dict[str, Any]:
        """构建监控报告（需在锁内调用）

        返回:
            dict[str, Any]: 监控报告
        """
        uptime = time.time() - self._data.start_time

        return {
            "uptime_seconds": round(uptime, 2),
            "uptime_human": self._format_uptime(uptime),
            "global": self._build_metrics_dict(self._data.global_metrics),
            "by_type": {
                cache_type: self._build_metrics_dict(metrics)
                for cache_type, metrics in self._data.type_metrics.items()
            },
        }

    def reset(self) -> None:
        """重置监控数据（线程安全）"""
        with self._sync_lock:
            self._data.reset()
        logger.info("缓存监控数据已重置", LOG_COMMAND)

    async def reset_async(self) -> None:
        """异步重置监控数据"""
        with self._sync_lock:
            self._data.reset()
        logger.info("缓存监控数据已重置", LOG_COMMAND)

    def log_report(self) -> None:
        """记录监控报告到日志"""
        report = self.get_report()
        logger.info(
            f"缓存监控报告 - 运行时间: {report['uptime_human']}, "
            f"命中率: {report['global']['hit_rate']}, "
            f"总操作: {report['global']['total_operations']}, "
            f"平均耗时: {report['global']['avg_time_ms']}ms, "
            f"P95延迟: {report['global']['latency']['p95_ms']}ms, "
            f"内存占用: {report['global']['memory']['estimated_size_mb']}MB",
            LOG_COMMAND,
        )

    @staticmethod
    def _format_uptime(seconds: float) -> str:
        """格式化运行时间

        参数:
            seconds: 秒数

        返回:
            str: 格式化的时间字符串
        """
        match seconds:
            case s if s < 60:
                return f"{s:.0f}秒"
            case s if s < 3600:
                return f"{s / 60:.0f}分钟"
            case s if s < 86400:
                return f"{s / 3600:.1f}小时"
            case _:
                return f"{seconds / 86400:.1f}天"


def monitor_operation(cache_type: str, operation: str) -> Callable:
    """监控操作装饰器

    参数:
        cache_type: 缓存类型
        operation: 操作类型 (get/set/delete)

    示例:
        ```python
        from liuying.services.cache.monitor import monitor_operation

        @monitor_operation("USER", "get")
        async def get_user(user_id: str):
            pass
        ```
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            monitor = CacheMonitor()
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                elapsed = time.time() - start_time

                match operation:
                    case "get":
                        op = "hit" if result is not None else "miss"
                        monitor.record(cache_type, op, elapsed)
                    case "set":
                        monitor.record(cache_type, "set", elapsed)
                    case "delete":
                        monitor.record(cache_type, "delete", elapsed)

                return result
            except Exception:
                # 异常情况下也记录耗时，用于分析错误操作的延迟
                elapsed = time.time() - start_time
                monitor.record_error(cache_type, elapsed)
                raise

        return wrapper

    return decorator
