"""
缓存指标数据结构

定义缓存监控的核心数据结构，包括指标和监控数据。
支持P50/P95/P99延迟统计和内存使用统计。
"""

from collections import defaultdict
from dataclasses import dataclass, field
import math
import sys
import time
from typing import Any


@dataclass(slots=True)
class LatencyStats:
    """延迟统计"""

    latencies: list[float] = field(default_factory=list)
    """延迟记录列表（毫秒）"""
    max_samples: int = 1000
    """最大采样数量"""
    _sorted_cache: list[float] | None = field(default=None, repr=False)
    """已排序的延迟缓存，新增记录时置空"""

    def record(self, latency_ms: float) -> None:
        """记录延迟

        参数:
            latency_ms: 延迟时间（毫秒）
        """
        if len(self.latencies) >= self.max_samples:
            self.latencies = self.latencies[-self.max_samples // 2 :]
        self.latencies.append(latency_ms)
        self._sorted_cache = None

    def _get_sorted(self) -> list[float]:
        """获取排序后的延迟列表（带缓存）

        返回:
            list[float]: 排序后的延迟列表
        """
        if self._sorted_cache is None:
            self._sorted_cache = sorted(self.latencies)
        return self._sorted_cache

    def percentile(self, p: float) -> float:
        """计算百分位延迟（使用线性插值法）

        参数:
            p: 百分位（0-100）

        返回:
            float: 延迟时间（毫秒）
        """
        if not self.latencies:
            return 0.0
        sorted_latencies = self._get_sorted()
        if len(sorted_latencies) == 1:
            return sorted_latencies[0]

        rank = (p / 100) * (len(sorted_latencies) - 1)
        lower_index = math.floor(rank)
        upper_index = math.ceil(rank)
        if lower_index == upper_index:
            return sorted_latencies[lower_index]

        weight = rank - lower_index
        return (
            sorted_latencies[lower_index] * (1 - weight)
            + sorted_latencies[upper_index] * weight
        )

    @property
    def p50(self) -> float:
        """P50延迟（毫秒）"""
        return self.percentile(50)

    @property
    def p95(self) -> float:
        """P95延迟（毫秒）"""
        return self.percentile(95)

    @property
    def p99(self) -> float:
        """P99延迟（毫秒）"""
        return self.percentile(99)

    @property
    def min(self) -> float:
        """最小延迟（毫秒）"""
        return self._get_sorted()[0] if self.latencies else 0.0

    @property
    def max(self) -> float:
        """最大延迟（毫秒）"""
        return self._get_sorted()[-1] if self.latencies else 0.0

    def clear(self) -> None:
        """清空延迟记录"""
        self.latencies.clear()
        self._sorted_cache = None


@dataclass(slots=True)
class MemoryStats:
    """内存使用统计"""

    total_entries: int = 0
    """总缓存条目数"""
    estimated_size_bytes: int = 0
    """估算内存占用（字节）"""
    max_entries: int = 0
    """最大条目数限制"""

    @property
    def estimated_size_mb(self) -> float:
        """估算内存占用（MB）"""
        return self.estimated_size_bytes / (1024 * 1024)

    @property
    def avg_entry_size(self) -> float:
        """平均条目大小（字节）"""
        return (
            self.estimated_size_bytes / self.total_entries
            if self.total_entries > 0
            else 0.0
        )

    def update(self, entries: int, size_bytes: int) -> None:
        """更新内存统计

        参数:
            entries: 条目数
            size_bytes: 内存占用（字节）
        """
        self.total_entries = entries
        self.estimated_size_bytes = size_bytes


def estimate_object_size(obj: Any, _seen: set[int] | None = None) -> int:
    """估算对象内存大小

    使用 _seen 集合检测循环引用，防止递归栈溢出。

    参数:
        obj: 要估算的对象
        _seen: 已访问对象的 id 集合（内部递归使用）

    返回:
        int: 估算大小（字节）
    """
    if obj is None:
        return 0

    obj_id = id(obj)
    if _seen is None:
        _seen = set()
    if obj_id in _seen:
        return 0
    _seen.add(obj_id)

    base_size = sys.getsizeof(obj)

    match obj:
        case dict():
            for k, v in obj.items():
                base_size += sys.getsizeof(k) + estimate_object_size(v, _seen)
        case list() | tuple() | set():
            for item in obj:
                base_size += estimate_object_size(item, _seen)
        case _ if hasattr(obj, "__dict__"):
            try:
                for attr_name, attr_val in obj.__dict__.items():
                    base_size += sys.getsizeof(attr_name) + estimate_object_size(
                        attr_val, _seen
                    )
            except Exception:
                pass

    return base_size


@dataclass(slots=True)
class CacheMetrics:
    """缓存指标"""

    hits: int = 0
    """缓存命中次数"""
    misses: int = 0
    """缓存未命中次数"""
    sets: int = 0
    """缓存设置次数"""
    deletes: int = 0
    """缓存删除次数"""
    errors: int = 0
    """缓存错误次数"""
    total_time: float = 0.0
    """总耗时（秒）"""
    avg_time: float = 0.0
    """平均耗时（秒）"""
    latency_stats: LatencyStats = field(default_factory=LatencyStats)
    """延迟统计"""
    memory_stats: MemoryStats = field(default_factory=MemoryStats)
    """内存统计"""

    @property
    def hit_rate(self) -> float:
        """缓存命中率"""
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0

    @property
    def total_operations(self) -> int:
        """总操作次数"""
        return self.hits + self.misses + self.sets + self.deletes

    def record_latency(self, elapsed_seconds: float) -> None:
        """记录操作延迟

        参数:
            elapsed_seconds: 耗时（秒）
        """
        latency_ms = elapsed_seconds * 1000
        self.latency_stats.record(latency_ms)


@dataclass(slots=True)
class CacheMonitorData:
    """缓存监控数据"""

    start_time: float = field(default_factory=time.time)
    """监控开始时间"""
    global_metrics: CacheMetrics = field(default_factory=CacheMetrics)
    """全局指标"""
    type_metrics: dict[str, CacheMetrics] = field(
        default_factory=lambda: defaultdict(CacheMetrics)
    )
    """按类型统计的指标"""

    def reset(self) -> None:
        """重置监控数据"""
        self.start_time = time.time()
        self.global_metrics = CacheMetrics()
        self.type_metrics.clear()
