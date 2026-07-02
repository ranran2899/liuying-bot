import asyncio
from collections import defaultdict, deque
from typing import Any

from liuying.utils.limiters import ConcurrencyLimiter


class EventLoopRateLimiter:
    """基于事件循环时间的速率限制器

    与 limiters.RateLimiter 不同，使用 asyncio 事件循环时间而非系统墙钟时间，
    适用于异步场景下更精确的速率控制。
    """

    def __init__(self, max_calls: int, time_window: float):
        self.requests: dict[Any, deque[float]] = defaultdict(deque)
        self.max_calls = max_calls
        self.time_window = time_window

    def check(self, key: Any) -> bool:
        """检查是否超出速率限制。如果未超出，则记录本次调用。"""
        now = asyncio.get_event_loop().time()
        while self.requests[key] and self.requests[key][0] <= now - self.time_window:
            self.requests[key].popleft()
        if len(self.requests[key]) < self.max_calls:
            self.requests[key].append(now)
            return True
        return False

    def left_time(self, key: Any) -> float:
        """计算距离下次可调用还需等待的时间"""
        if self.requests[key]:
            loop_time = asyncio.get_event_loop().time()
            return max(0.0, self.requests[key][0] + self.time_window - loop_time)
        return 0.0


__all__ = ["ConcurrencyLimiter", "EventLoopRateLimiter"]
