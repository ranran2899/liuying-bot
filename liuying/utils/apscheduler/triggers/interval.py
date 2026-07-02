"""
时间间隔触发器
支持固定时间间隔的定时任务触发
"""

from datetime import datetime, timedelta
import random
from typing import Any, Self

from liuying.utils.apscheduler.triggers.base import (
    BaseTrigger,
    TriggerResult,
    register_trigger,
)


@register_trigger("interval")
class IntervalTrigger(BaseTrigger):
    """
    时间间隔触发器

    支持以周、天、小时、分钟、秒为单位的时间间隔触发。
    可设置开始时间和结束时间限制任务执行范围。
    """

    def __init__(
        self,
        weeks: int = 0,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        start_date: datetime | str | None = None,
        end_date: datetime | str | None = None,
        timezone: str | None = None,
        jitter: int | None = None,
    ) -> None:
        super().__init__(start_date, end_date, timezone)

        self._interval = timedelta(
            weeks=weeks, days=days, hours=hours,
            minutes=minutes, seconds=seconds,
        )

        if self._interval.total_seconds() <= 0:
            self._interval = timedelta(seconds=1)

        self._jitter = jitter

    @property
    def interval(self) -> timedelta:
        """获取时间间隔"""
        return self._interval

    @property
    def interval_seconds(self) -> float:
        """获取时间间隔（秒）"""
        return self._interval.total_seconds()

    def get_next_run_time(self, previous_time: datetime | None = None) -> TriggerResult:
        """获取下次运行时间"""
        now = datetime.now()

        if previous_time is None:
            # 新任务：从下一个间隔开始，避免启动时立即执行
            if self._start_date and now < self._start_date:
                next_time = self._start_date
            else:
                # 返回下一个间隔时间，而不是当前时间
                next_time = now + self._interval
        else:
            if previous_time.tzinfo is not None:
                previous_time = previous_time.replace(tzinfo=None)
            next_time = previous_time + self._interval

        if self._end_date and next_time > self._end_date:
            return TriggerResult(next_run_time=None, should_run=False)

        if self._jitter:
            jitter_seconds = random.uniform(-self._jitter, self._jitter)
            next_time = next_time + timedelta(seconds=jitter_seconds)

        return TriggerResult(next_run_time=next_time, should_run=False)

    def to_config(self) -> dict[str, Any]:
        """转换为配置字典"""
        config: dict[str, Any] = {
            "weeks": self._interval.days // 7,
            "days": self._interval.days % 7,
            "hours": self._interval.seconds // 3600,
            "minutes": (self._interval.seconds % 3600) // 60,
            "seconds": self._interval.seconds % 60,
        }

        if self._start_date:
            config["start_date"] = self._start_date.isoformat()
        if self._end_date:
            config["end_date"] = self._end_date.isoformat()
        if self._jitter:
            config["jitter"] = self._jitter

        return config

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> Self:
        """从配置创建触发器"""
        return cls(
            weeks=config.get("weeks", 0),
            days=config.get("days", 0),
            hours=config.get("hours", 0),
            minutes=config.get("minutes", 0),
            seconds=config.get("seconds", 0),
            start_date=config.get("start_date"),
            end_date=config.get("end_date"),
            timezone=config.get("timezone"),
            jitter=config.get("jitter"),
        )
