"""Provider健康统计与动态优先级

基于 EMA 延迟平滑和失败率计算 provider 动态优先级。
使用内存缓存存储统计数据，重启后重新积累。

数据流：
- 每次 LLM 请求后调用 record_request_result 记录结果
- 候选排序时调用 compute_effective_priority 计算动态优先级
- 样本数不足时直接返回 base_priority（冷启动保护）
"""

import random
import threading
import time
from typing import Any

from liuying.utils.log import logger

__all__ = [
    "ProviderHealth",
    "provider_health",
]


_EMA_ALPHA = 0.3
"""EMA平滑系数：新样本权重30%，老平均权重70%"""

_MIN_SAMPLES = 3
"""冷启动保护最小样本数"""

_LATENCY_THRESHOLD_MS = 1000.0
"""延迟惩罚阈值（毫秒）"""

_LATENCY_PENALTY_DIVISOR = 500.0
"""延迟惩罚除数"""

_FAILURE_PENALTY_MAX = 10.0
"""失败率惩罚上限"""

_NEVER_SUCCESS_EXTRA = 100.0
"""从未成功的额外惩罚"""

_COOLDOWN_BASE = 60.0
"""指数退避基数（秒）"""

_COOLDOWN_MAX = 1800.0
"""指数退避上限（秒）"""

_COOLDOWN_MIN = 15.0
"""冷却下限（秒）"""

_RATE_LIMIT_BASE = 600.0
"""429限流基础冷却（秒）"""

_JITTER_RATIO = 0.2
"""抖动比例（±20%）"""


class ProviderHealth:
    """Provider健康统计管理器

    封装 provider 请求结果记录、健康统计查询、动态优先级计算
    和冷却时间计算。所有状态存储在内存中，重启后重新积累。

    核心算法：
    - EMA平滑：avg = α·new + (1-α)·old，避免单次极端值影响排序
    - 动态优先级：effective = base + latency_penalty + failure_penalty
    - 冷启动保护：样本数 < 3 时直接返回 base_priority
    - 从未成功惩罚：样本足够但成功数为0时额外+100，避免"失败得快"的provider排在前面
    """

    def __init__(self) -> None:
        """初始化Provider健康管理器"""
        self._stats: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def classify_error(exc: Exception | str | None) -> str:
        """将异常归类为有限的 kind 标签

        参数:
            exc: 异常对象或错误文本

        返回:
            str: 错误类型标签（timeout/rate_limit/5xx/4xx/connect/other）
        """
        if exc is None:
            return ""
        text = str(exc).lower()
        if "timeout" in text or "timed out" in text:
            return "timeout"
        if "connect" in text or "tls" in text:
            return "connect"
        if (
            "429" in text
            or "rate limit" in text
            or "too many requests" in text
        ):
            return "rate_limit"
        response = getattr(exc, "response", None)
        status = (
            getattr(response, "status_code", None)
            if response is not None
            else None
        )
        try:
            code = int(status or 0)
        except (TypeError, ValueError):
            code = 0
        if code == 429:
            return "rate_limit"
        if 500 <= code < 600:
            return "5xx"
        if 400 <= code < 500:
            return "4xx"
        return "other"

    def record_request_result(
        self,
        *,
        provider_name: str,
        latency_ms: float,
        success: bool,
        error_kind: str = "",
    ) -> None:
        """记录一次真实请求结果

        参数:
            provider_name: provider名称
            latency_ms: 请求延迟（毫秒）
            success: 是否成功
            error_kind: 错误类型标签
        """
        name = str(provider_name or "").strip()
        if not name:
            return
        lat = max(0.0, float(latency_ms or 0))
        now = time.time()
        try:
            with self._lock:
                row = self._stats.get(name)
                if row is None:
                    self._stats[name] = {
                        "sample_count": 1,
                        "success_count": 1 if success else 0,
                        "failure_count": 0 if success else 1,
                        "avg_latency_ms": lat,
                        "last_request_at": now,
                        "last_success_at": (
                            now if success else 0.0
                        ),
                        "last_failure_at": (
                            0.0 if success else now
                        ),
                        "last_error_kind": str(error_kind or "")[
                            :32
                        ],
                        "last_seen_at": now,
                    }
                else:
                    row["sample_count"] = (
                        int(row["sample_count"]) + 1
                    )
                    row["success_count"] = int(
                        row["success_count"]
                    ) + (1 if success else 0)
                    row["failure_count"] = int(
                        row["failure_count"]
                    ) + (0 if success else 1)
                    old_avg = float(row["avg_latency_ms"] or 0)
                    new_avg = (
                        lat
                        if old_avg <= 0
                        else _EMA_ALPHA * lat
                        + (1 - _EMA_ALPHA) * old_avg
                    )
                    row["avg_latency_ms"] = new_avg
                    row["last_request_at"] = now
                    if success:
                        row["last_success_at"] = now
                    else:
                        row["last_failure_at"] = now
                    row["last_error_kind"] = str(error_kind or "")[
                        :32
                    ]
                    row["last_seen_at"] = now
        except Exception as e:
            logger.debug(
                f"Provider健康统计写入失败 {name}: {e}",
                command="AI",
                e=e,
            )

    def get_stats(
        self, provider_name: str
    ) -> dict[str, Any] | None:
        """获取provider健康统计

        参数:
            provider_name: provider名称

        返回:
            dict | None: 统计字典，无数据返回None
        """
        name = str(provider_name or "").strip()
        if not name:
            return None
        with self._lock:
            row = self._stats.get(name)
            if row is None:
                return None
            return dict(row)

    def get_all_stats(self) -> dict[str, dict[str, Any]]:
        """获取所有provider健康统计

        返回:
            dict: {provider_name: stats_dict}
        """
        with self._lock:
            return {
                name: dict(stats)
                for name, stats in self._stats.items()
            }

    def reset_stats(self, provider_name: str) -> bool:
        """重置provider统计

        参数:
            provider_name: provider名称

        返回:
            bool: 是否成功重置
        """
        name = str(provider_name or "").strip()
        if not name:
            return False
        with self._lock:
            if name in self._stats:
                del self._stats[name]
                return True
            return False

    def compute_effective_priority(
        self,
        provider_name: str,
        base_priority: float,
        *,
        min_samples: int = _MIN_SAMPLES,
    ) -> float:
        """计算provider的动态优先级

        effective = base + latency_penalty + failure_penalty
        样本数不足时直接返回base（冷启动保护）。

        参数:
            provider_name: provider名称
            base_priority: 基础优先级
            min_samples: 最小样本数

        返回:
            float: 动态优先级（越大越靠后）
        """
        base = float(base_priority or 0)
        stats = self.get_stats(provider_name)
        if not stats:
            return base
        sample_count = int(stats.get("sample_count", 0) or 0)
        if sample_count < max(1, int(min_samples or 3)):
            return base
        avg_latency = float(
            stats.get("avg_latency_ms", 0) or 0
        )
        success_count = int(
            stats.get("success_count", 0) or 0
        )
        success_rate = (
            success_count / sample_count
            if sample_count > 0
            else 1.0
        )
        latency_penalty = max(
            0.0,
            (avg_latency - _LATENCY_THRESHOLD_MS)
            / _LATENCY_PENALTY_DIVISOR,
        )
        failure_penalty = (
            1.0 - success_rate
        ) * _FAILURE_PENALTY_MAX
        if success_count <= 0:
            failure_penalty += _NEVER_SUCCESS_EXTRA
        return base + latency_penalty + failure_penalty

    @staticmethod
    def compute_cooldown_seconds(
        failures: int,
        *,
        is_rate_limit: bool = False,
        retry_after: float = 0.0,
    ) -> float:
        """计算指数退避冷却时间

        参数:
            failures: 连续失败次数
            is_rate_limit: 是否为429限流
            retry_after: 服务端Retry-After值

        返回:
            float: 冷却时间（秒）
        """
        n = max(1, int(failures or 1))
        if is_rate_limit:
            base = max(_RATE_LIMIT_BASE, float(retry_after or 0))
            base = min(_COOLDOWN_MAX, base)
        else:
            base = min(_COOLDOWN_MAX, _COOLDOWN_BASE * (2 ** (n - 1)))
        jitter = base * _JITTER_RATIO
        delta = random.uniform(-jitter, jitter)
        cooldown = max(_COOLDOWN_MIN, base + delta)
        if is_rate_limit and retry_after:
            cooldown = max(
                cooldown,
                min(_COOLDOWN_MAX, float(retry_after or 0)),
            )
        return cooldown


provider_health = ProviderHealth()
"""Provider健康管理器单例"""
