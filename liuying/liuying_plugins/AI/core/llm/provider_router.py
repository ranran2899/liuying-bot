"""Provider路由

多provider容错路由：失败缓存（cooldown）+ 指数退避 +
同优先级轮询 + 冷却降级不剔除。
基于 EMA 延迟平滑与失败率计算动态优先级，
状态存于内存，重启后重新积累。
"""

import asyncio
from dataclasses import dataclass
import random
import re
import threading
import time

from liuying.utils.log import logger

__all__ = [
    "ProviderRouter",
    "ProviderState",
    "provider_router",
]


_MAX_RETRIES = 2
"""单provider最大重试次数"""

_EMA_ALPHA = 0.3
"""EMA平滑系数：新样本权重30%，老平均权重70%"""

_MIN_SAMPLES = 3
"""动态优先级冷启动保护最小样本数"""

_LATENCY_THRESHOLD_MS = 1000.0
"""延迟惩罚阈值（毫秒）"""

_LATENCY_PENALTY_DIVISOR = 500.0
"""延迟惩罚除数"""

_FAILURE_PENALTY_MAX = 10.0
"""失败率惩罚上限"""

_COOLING_PENALTY = 1000.0
"""冷却provider的额外惩罚（降级到最后但不剔除）"""

_NEVER_SUCCESS_EXTRA = 100.0
"""从未成功的额外惩罚，避免"失败得快"的provider排在前面"""

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
    if isinstance(status, int | float) and not isinstance(status, bool):
        code = int(status)
    else:
        code = 0
    if code == 429:
        return "rate_limit"
    if 500 <= code < 600:
        return "5xx"
    if 400 <= code < 500:
        return "4xx"
    return "other"


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


@dataclass(slots=True)
class ProviderState:
    """Provider运行状态与健康统计

    Attributes:
        name: provider名
        consecutive_failures: 连续失败次数
        cooldown_until: 冷却截止时间戳
        retry_after: 限流Retry-After
        sample_count: 请求样本数
        success_count: 成功次数
        avg_latency_ms: EMA平滑平均延迟（毫秒）
    """

    name: str
    consecutive_failures: int = 0
    cooldown_until: float = 0.0
    retry_after: float = 0.0
    sample_count: int = 0
    success_count: int = 0
    avg_latency_ms: float = 0.0


class ProviderRouter:
    """Provider路由管理器

    管理多provider的失败缓存、轮询、容错切换与动态优先级。

    核心算法：
    - EMA平滑：avg = α·new + (1-α)·old，避免单次极端值影响排序
    - 动态优先级：effective = base + latency_penalty + failure_penalty
    - 冷启动保护：样本数不足时直接使用 base_priority
    """

    def __init__(self) -> None:
        """初始化Provider路由管理器"""
        self._states: dict[str, ProviderState] = {}
        self._lock = threading.RLock()
        self._rotation_cursor = 0

    def get_state(self, name: str) -> ProviderState:
        """获取provider状态（不存在时创建）

        参数:
            name: provider名

        返回:
            ProviderState: 状态对象
        """
        with self._lock:
            state = self._states.get(name)
            if state is None:
                state = ProviderState(name=name)
                self._states[name] = state
            return state

    def is_cooling(self, name: str, *, now_ts: float | None = None) -> bool:
        """判断provider是否在冷却期

        参数:
            name: provider名
            now_ts: 当前时间戳，None用time.time()

        返回:
            bool: 是否在冷却期
        """
        now_value = time.time() if now_ts is None else float(now_ts)
        state = self.get_state(name)
        return state.cooldown_until > now_value

    def record_success(
        self, name: str, latency: float = 0.0
    ) -> None:
        """记录成功调用

        参数:
            name: provider名
            latency: 调用延迟（秒）
        """
        with self._lock:
            state = self.get_state(name)
            state.consecutive_failures = 0
            state.cooldown_until = 0.0
            state.retry_after = 0.0
            state.success_count += 1
            state.sample_count += 1
            latency_ms = max(0.0, latency * 1000.0)
            if latency_ms > 0:
                state.avg_latency_ms = (
                    latency_ms
                    if state.avg_latency_ms <= 0
                    else _EMA_ALPHA * latency_ms
                    + (1 - _EMA_ALPHA) * state.avg_latency_ms
                )

    def record_failure(
        self,
        name: str,
        *,
        is_rate_limit: bool = False,
        retry_after: float = 0.0,
    ) -> None:
        """记录失败调用并计算冷却

        指数退避冷却加入抖动，避免多个provider同时恢复造成惊群。

        参数:
            name: provider名
            is_rate_limit: 是否429限流
            retry_after: Retry-After秒数
        """
        with self._lock:
            state = self.get_state(name)
            state.consecutive_failures += 1
            state.sample_count += 1
            cooldown = compute_cooldown_seconds(
                state.consecutive_failures,
                is_rate_limit=is_rate_limit,
                retry_after=retry_after,
            )
            state.cooldown_until = time.time() + cooldown
            state.retry_after = retry_after

    def _effective_priority(
        self, state: ProviderState, base_priority: float
    ) -> float:
        """计算provider的动态优先级

        effective = base + latency_penalty + failure_penalty，
        样本数不足时直接返回base（冷启动保护）。

        参数:
            state: provider运行状态
            base_priority: 基础优先级

        返回:
            float: 动态优先级（越大越靠后）
        """
        base = float(base_priority or 0)
        if state.sample_count < _MIN_SAMPLES:
            return base
        success_rate = state.success_count / state.sample_count
        latency_penalty = max(
            0.0,
            (state.avg_latency_ms - _LATENCY_THRESHOLD_MS)
            / _LATENCY_PENALTY_DIVISOR,
        )
        failure_penalty = (1.0 - success_rate) * _FAILURE_PENALTY_MAX
        if state.success_count <= 0:
            failure_penalty += _NEVER_SUCCESS_EXTRA
        return base + latency_penalty + failure_penalty

    def sort_candidates(
        self,
        providers: list[str],
    ) -> list[str]:
        """按有效优先级排序provider候选列表

        结合动态优先级（EMA延迟+失败率）与本地冷却状态排序。
        冷却的provider降级到最后但不剔除；同分轮询负载均衡。

        参数:
            providers: provider名列表

        返回:
            list[str]: 排序后的候选列表
        """
        now_ts = time.time()
        decorated: list[tuple[float, str]] = []
        for idx, name in enumerate(providers):
            state = self.get_state(name)
            effective = self._effective_priority(state, float(idx))
            if state.cooldown_until > now_ts:
                effective += _COOLING_PENALTY
            decorated.append((effective, name))

        decorated.sort(key=lambda x: (x[0], x[1]))
        if not decorated:
            return list(providers)

        top_eff = decorated[0][0]
        top_tier = [item[1] for item in decorated if item[0] == top_eff]
        lower_tiers = [
            item[1] for item in decorated if item[0] > top_eff
        ]

        if len(top_tier) > 1:
            with self._lock:
                cursor = self._rotation_cursor % len(top_tier)
                self._rotation_cursor = (
                    self._rotation_cursor + 1
                ) % len(top_tier)
            rotated = top_tier[cursor:] + top_tier[:cursor]
        else:
            rotated = top_tier

        return rotated + lower_tiers

    async def call_with_failover(
        self,
        providers: list[str],
        call_fn,
        *args,
        **kwargs,
    ):
        """带容错切换的调用

        按sort_candidates顺序尝试，失败时记录并切换到下一个。

        参数:
            providers: provider名列表
            call_fn: 调用函数（接受provider名和*args/**kwargs）
            *args: 位置参数
            **kwargs: 关键字参数

        返回:
            Any: 调用结果

        异常:
            RuntimeError: 所有provider都失败
        """
        candidates = self.sort_candidates(providers)
        last_error: Exception | None = None

        for name in candidates:
            for attempt in range(_MAX_RETRIES):
                start = time.time()
                try:
                    result = await call_fn(name, *args, **kwargs)
                    self.record_success(name, latency=time.time() - start)
                    return result
                except Exception as exc:
                    last_error = exc
                    error_kind = classify_error(exc)
                    self.record_failure(
                        name,
                        is_rate_limit=error_kind == "rate_limit",
                        retry_after=self._extract_retry_after(exc),
                    )
                    logger.warning(
                        f"provider {name} 第{attempt+1}次失败: {exc}",
                        command="AI",
                        e=exc,
                    )
                    if error_kind == "rate_limit":
                        break
                    await asyncio.sleep(min(1.0 * (attempt + 1), 3.0))

        raise RuntimeError(
            f"所有provider失败: {candidates}，最后错误: {last_error}"
        )

    @staticmethod
    def _extract_retry_after(exc: Exception) -> float:
        """从异常中提取Retry-After

        参数:
            exc: 异常

        返回:
            float: Retry-After秒数
        """
        msg = str(exc).lower()
        for keyword in ["retry after", "retry-after"]:
            if keyword in msg:
                match = re.search(r"(\d+)", msg.split(keyword)[1])
                if match:
                    return float(match.group(1))
        return 0.0


provider_router = ProviderRouter()
"""Provider路由单例"""
