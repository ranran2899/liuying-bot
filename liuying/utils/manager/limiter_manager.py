import time
from collections import defaultdict, deque
from typing import Any

type RateMap = dict[Any, deque[float]]


class EventLoopRateLimiter:
    """基于事件循环时间的速率限制器

    使用单调时钟（与事件循环时间一致）而非系统墙钟时间，
    适用于异步场景下更精确的速率控制。
    """

    def __init__(self, max_calls: int, time_window: float):
        self.requests: RateMap = defaultdict(deque)
        self.max_calls = max_calls
        self.time_window = time_window

    def check(self, key: Any) -> bool:
        """检查是否超出速率限制。如果未超出，则记录本次调用。"""
        now = time.monotonic()
        queue = self.requests.get(key)
        if queue is None:
            if self.max_calls <= 0:
                return False
            self.requests[key] = deque((now,))
            return True
        while queue and queue[0] <= now - self.time_window:
            queue.popleft()
        if len(queue) < self.max_calls:
            queue.append(now)
            return True
        if not queue:
            del self.requests[key]
        return False

    def left_time(self, key: Any) -> float:
        """计算距离下次可调用还需等待的时间"""
        if queue := self.requests.get(key):
            return max(0.0, queue[0] + self.time_window - time.monotonic())
        return 0.0


__all__ = ["EventLoopRateLimiter"]
