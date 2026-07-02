"""Provider路由

多provider容错路由：失败缓存（cooldown）+ 指数退避 +
同优先级轮询 + 冷却降级不剔除。
"""

import asyncio
from dataclasses import dataclass
import re
import threading
import time
from typing import Any

from liuying.utils.log import logger

__all__ = [
    "ProviderRouter",
    "ProviderState",
    "provider_router",
]


_RATE_LIMIT_DEFAULT_COOLDOWN = 600.0
"""429限流默认冷却（秒）"""


_RATE_LIMIT_MAX_COOLDOWN = 1800.0
"""429限流最大冷却（秒）"""


_EXPONENTIAL_BASE = 60.0
"""指数退避基数（秒）"""


_EXPONENTIAL_MAX = 1800.0
"""指数退避上限（秒）"""


_MAX_RETRIES = 2
"""单provider最大重试次数"""


@dataclass(slots=True)
class ProviderState:
    """Provider健康状态

    Attributes:
        name: provider名
        consecutive_failures: 连续失败次数
        cooldown_until: 冷却截止时间戳
        retry_after: 限流Retry-After
        last_latency: 最近延迟（秒）
        success_count: 成功次数
    """

    name: str
    consecutive_failures: int = 0
    cooldown_until: float = 0.0
    retry_after: float = 0.0
    last_latency: float = 0.0
    success_count: int = 0


class ProviderRouter:
    """Provider路由管理器

    管理多provider的失败缓存、轮询、容错切换。
    """

    def __init__(self) -> None:
        """初始化Provider路由管理器"""
        self._states: dict[str, ProviderState] = {}
        self._lock = threading.RLock()
        self._rotation_cursor = 0
        self._latency_alpha = 0.3

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
            latency: 调用延迟
        """
        with self._lock:
            state = self.get_state(name)
            state.consecutive_failures = 0
            state.cooldown_until = 0.0
            state.retry_after = 0.0
            state.success_count += 1
            if latency > 0:
                state.last_latency = (
                    state.last_latency * (1 - self._latency_alpha)
                    + latency * self._latency_alpha
                    if state.last_latency > 0
                    else latency
                )

    def record_failure(
        self,
        name: str,
        *,
        is_rate_limit: bool = False,
        retry_after: float = 0.0,
    ) -> None:
        """记录失败调用并计算冷却

        参数:
            name: provider名
            is_rate_limit: 是否429限流
            retry_after: Retry-After秒数
        """
        with self._lock:
            state = self.get_state(name)
            state.consecutive_failures += 1
            now_ts = time.time()

            if is_rate_limit:
                cooldown = max(
                    _RATE_LIMIT_DEFAULT_COOLDOWN,
                    float(retry_after or 0.0),
                )
                cooldown = min(cooldown, _RATE_LIMIT_MAX_COOLDOWN)
            else:
                backoff = _EXPONENTIAL_BASE * (
                    2 ** (state.consecutive_failures - 1)
                )
                cooldown = min(backoff, _EXPONENTIAL_MAX)

            state.cooldown_until = now_ts + cooldown
            state.retry_after = retry_after

    def sort_candidates(
        self,
        providers: list[str],
    ) -> list[str]:
        """按有效优先级排序provider候选列表

        冷却的provider降级到最后但不剔除。

        参数:
            providers: provider名列表

        返回:
            list[str]: 排序后的候选列表
        """
        now_ts = time.time()
        decorated: list[tuple[float, str, bool]] = []
        for name in providers:
            state = self.get_state(name)
            cooling = state.cooldown_until > now_ts
            penalty = state.consecutive_failures * 10.0
            if state.success_count == 0 and state.consecutive_failures > 0:
                penalty += 100.0
            if cooling:
                penalty += 100.0
            effective = penalty + state.last_latency
            decorated.append((effective, name, cooling))

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
        call_fn: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
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
                    latency = time.time() - start
                    self.record_success(name, latency=latency)
                    return result
                except Exception as exc:
                    last_error = exc
                    is_rate = self._is_rate_limit(exc)
                    retry_after = self._extract_retry_after(exc)
                    self.record_failure(
                        name,
                        is_rate_limit=is_rate,
                        retry_after=retry_after,
                    )
                    logger.warning(
                        f"provider {name} 第{attempt+1}次失败: {exc}",
                        command="AI",
                        e=exc,
                    )
                    if is_rate:
                        break
                    await asyncio.sleep(min(1.0 * (attempt + 1), 3.0))

        raise RuntimeError(
            f"所有provider失败: {candidates}，最后错误: {last_error}"
        )

    def _is_rate_limit(self, exc: Exception) -> bool:
        """判断是否429限流

        参数:
            exc: 异常

        返回:
            bool: 是否限流
        """
        msg = str(exc).lower()
        return (
            "429" in msg
            or "rate limit" in msg
            or "too many requests" in msg
        )

    def _extract_retry_after(self, exc: Exception) -> float:
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
