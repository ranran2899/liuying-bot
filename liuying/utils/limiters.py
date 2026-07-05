import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
import time
from typing import Any

from liuying.utils.log import logger


@dataclass(slots=True)
class FreqLimiter:
    """命令冷却，检测用户是否处于冷却状态"""

    default_cd: int
    next_time: dict[Any, float] = field(
        default_factory=lambda: defaultdict(float)
    )

    def check(self, key: Any) -> bool:
        return time.time() >= self.next_time[key]

    def start_cd(self, key: Any, cd_time: int = 0):
        self.next_time[key] = time.time() + (
            cd_time if cd_time > 0 else self.default_cd
        )

    def left_time(self, key: Any) -> float:
        return max(0.0, self.next_time[key] - time.time())


@dataclass(slots=True)
class CountLimiter:
    """每日调用命令次数限制"""

    max: int
    today: int = -1
    count: dict[Any, int] = field(default_factory=lambda: defaultdict(int))

    def _refresh_day(self):
        """若日期变化则清空当日计数"""
        day = datetime.now().day
        if day != self.today:
            self.today = day
            self.count.clear()

    def check(self, key: Any) -> bool:
        self._refresh_day()
        return self.count[key] < self.max

    def get_num(self, key: Any) -> int:
        self._refresh_day()
        return self.count[key]

    def increase(self, key: Any, num: int = 1):
        self._refresh_day()
        self.count[key] += num

    def reset(self, key: Any):
        self.count[key] = 0


@dataclass(slots=True)
class UserBlockLimiter:
    """检测用户是否正在调用命令 (简单阻塞锁)"""

    flag_data: dict[Any, bool] = field(
        default_factory=lambda: defaultdict(bool)
    )
    time: dict[Any, float] = field(
        default_factory=lambda: defaultdict(float)
    )

    def set_true(self, key: Any):
        self.time[key] = time.time()
        self.flag_data[key] = True

    def set_false(self, key: Any):
        self.flag_data[key] = False

    def check(self, key: Any) -> bool:
        if self.flag_data[key] and time.time() - self.time[key] > 30:
            self.set_false(key)
        return not self.flag_data[key]


@dataclass(slots=True)
class RateLimiter:
    """基于时间窗口的速率限制器"""

    max_calls: int
    time_window: int
    requests: dict[Any, deque[float]] = field(
        default_factory=lambda: defaultdict(deque)
    )

    def check(self, key: Any) -> bool:
        """检查是否超出速率限制。如果未超出，则记录本次调用。"""
        now = time.time()
        queue = self.requests[key]
        while queue and queue[0] <= now - self.time_window:
            queue.popleft()
        if len(queue) < self.max_calls:
            queue.append(now)
            return True
        return False

    def left_time(self, key: Any) -> float:
        """计算距离下次可调用还需等待的时间"""
        if queue := self.requests[key]:
            return max(0.0, queue[0] + self.time_window - time.time())
        return 0.0


@dataclass(slots=True)
class ConcurrencyLimiter:
    """基于 asyncio.Semaphore 的并发限制器"""

    max_concurrent: int
    _semaphores: dict[Any, asyncio.Semaphore] = field(default_factory=dict)

    def _get_semaphore(self, key: Any) -> asyncio.Semaphore:
        if key not in self._semaphores:
            self._semaphores[key] = asyncio.Semaphore(self.max_concurrent)
        return self._semaphores[key]

    async def acquire(self, key: Any):
        """获取一个信号量，如果达到并发上限则会阻塞等待。"""
        await self._get_semaphore(key).acquire()

    def release(self, key: Any):
        """释放一个信号量。"""
        semaphore = self._semaphores.get(key)
        if not semaphore:
            logger.warning(
                f"尝试释放键 '{key}' 的信号量时，该键不存在。",
                command="ConcurrencyLimiter",
            )
            return
        try:
            semaphore.release()
        except ValueError:
            logger.warning(
                f"尝试释放键 '{key}' 的信号量时，计数已经为零。",
                command="ConcurrencyLimiter",
            )
