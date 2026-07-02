"""
Cron 表达式触发器
支持标准 cron 表达式的定时任务触发，采用字段级跳跃算法实现高性能计算

标准 cron 默认值规则：
- 日期字段（year/month/day/day_of_week）未指定时匹配所有值
- 时间字段（hour/minute/second）未指定时默认为 0
"""

import bisect
import calendar
from datetime import datetime, timedelta
from typing import Any, Self

from liuying.utils.apscheduler.triggers.base import (
    BaseTrigger,
    TriggerResult,
    register_trigger,
)


class CronField:
    """单个 Cron 字段"""

    def __init__(self, name: str, min_val: int, max_val: int):
        self.name = name
        self.min_val = min_val
        self.max_val = max_val
        self.values: set[int] | None = None
        self._sorted_values: list[int] | None = None

    def parse(self, value: int | str | None) -> None:
        """解析字段值"""
        if value is None:
            self.values = None
            self._sorted_values = None
            return
        if isinstance(value, int):
            self.values = {value}
            self._sorted_values = [value]
            return
        if isinstance(value, str):
            self.values = self._parse_expression(value)
            self._sorted_values = sorted(self.values) if self.values else None

    def _parse_expression(self, expr: str) -> set[int]:
        """解析 cron 表达式字段（支持 * / - , 语法）"""
        result: set[int] = set()
        for part in expr.split(","):
            part = part.strip()
            if part == "*":
                result.update(range(self.min_val, self.max_val + 1))
            elif "/" in part:
                base, step = part.split("/", 1)
                step = int(step)
                if base == "*":
                    result.update(range(self.min_val, self.max_val + 1, step))
                else:
                    start = int(base)
                    result.update(range(start, self.max_val + 1, step))
            elif "-" in part:
                start, end = part.split("-", 1)
                result.update(range(int(start), int(end) + 1))
            else:
                result.add(int(part))
        return result

    def matches(self, value: int) -> bool:
        """检查值是否匹配"""
        if self.values is None:
            return True
        return value in self.values

    def get_next(self, value: int) -> int | None:
        """获取大于等于value的下一个值，找不到返回None"""
        if self.values is None:
            return value
        if not self._sorted_values:
            return None
        idx = bisect.bisect_left(self._sorted_values, value)
        if idx < len(self._sorted_values):
            return self._sorted_values[idx]
        return None

    def get_next_wrap(self, value: int) -> int:
        """获取大于等于value的下一个值，找不到回绕返回最小值"""
        if self.values is None:
            return value
        if not self._sorted_values:
            return self.min_val
        idx = bisect.bisect_left(self._sorted_values, value)
        if idx < len(self._sorted_values):
            return self._sorted_values[idx]
        return self._sorted_values[0]


@register_trigger("cron")
class CronTrigger(BaseTrigger):
    """
    Cron 表达式触发器

    支持标准 cron 表达式格式，可指定年、月、日、周、星期、时、分、秒。

    默认值规则（与 APScheduler 标准一致）：
    - 日期字段未指定时匹配所有值（year/month/day/day_of_week → *）
    - 时间字段未指定时默认为 0（hour/minute/second → 0）

    采用字段级跳跃算法，避免逐秒遍历，大幅提升计算性能。
    """

    def __init__(
        self,
        year: int | str | None = None,
        month: int | str | None = None,
        day: int | str | None = None,
        week: int | str | None = None,
        day_of_week: int | str | None = None,
        hour: int | str | None = None,
        minute: int | str | None = None,
        second: int | str | None = None,
        start_date: datetime | str | None = None,
        end_date: datetime | str | None = None,
        timezone: str | None = None,
    ) -> None:
        super().__init__(start_date, end_date, timezone)

        self.year_field = CronField("year", 1970, 2099)
        self.month_field = CronField("month", 1, 12)
        self.day_field = CronField("day", 1, 31)
        self.day_of_week_field = CronField("day_of_week", 0, 6)
        self.hour_field = CronField("hour", 0, 23)
        self.minute_field = CronField("minute", 0, 59)
        self.second_field = CronField("second", 0, 59)

        self.year_field.parse(year)
        self.month_field.parse(month)
        self.day_field.parse(day)
        self.day_of_week_field.parse(day_of_week)
        self.hour_field.parse(hour if hour is not None else 0)
        self.minute_field.parse(minute if minute is not None else 0)
        self.second_field.parse(second if second is not None else 0)

    def _get_next_candidate(self, start_dt: datetime) -> datetime | None:
        """获取下一个匹配的时间"""
        dt = start_dt.replace(microsecond=0)
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)

        max_iterations = 1000
        for _ in range(max_iterations):
            if self._end_date and dt > self._end_date:
                return None
            if self._start_date and dt < self._start_date:
                dt = self._start_date.replace(microsecond=0)
                continue

            result = self._try_advance(dt)
            if result is not None:
                return result

            dt = self._next_day(dt)

        return None

    def _try_advance(self, dt: datetime) -> datetime | None:
        """尝试从当前时间推进到下一个匹配时间"""
        dt = dt.replace(microsecond=0)

        if not self.year_field.matches(dt.year):
            next_year = self.year_field.get_next(dt.year)
            if next_year is None:
                return None
            return datetime(next_year, 1, 1, 0, 0, 0)

        if not self.month_field.matches(dt.month):
            return self._next_month(dt)

        return self._try_advance_day(dt)

    def _next_month(self, dt: datetime) -> datetime:
        """推进到下一个月"""
        next_month = self.month_field.get_next_wrap(dt.month + 1)
        if next_month <= dt.month:
            next_year = dt.year + 1
            if not self.year_field.matches(next_year):
                next_year = self.year_field.get_next(next_year)
                if next_year is None:
                    return dt.replace(
                        year=dt.year + 1, month=1, day=1,
                        hour=0, minute=0, second=0
                    )
            return datetime(next_year, next_month, 1, 0, 0, 0)
        return dt.replace(month=next_month, day=1, hour=0, minute=0, second=0)

    def _next_day(self, dt: datetime) -> datetime:
        """推进到下一天"""
        next_dt = dt + timedelta(days=1)
        return next_dt.replace(hour=0, minute=0, second=0)

    def _try_advance_day(self, dt: datetime) -> datetime | None:
        """尝试推进到当天匹配的时间"""
        max_days = 366
        for _ in range(max_days):
            max_day = calendar.monthrange(dt.year, dt.month)[1]

            if not self.day_field.matches(dt.day) or dt.day > max_day:
                dt = self._next_day(dt)
                continue

            if not self.day_of_week_field.matches(dt.weekday()):
                dt = self._next_day(dt)
                continue

            result = self._try_advance_time(dt)
            if result is not None:
                return result

            dt = self._next_day(dt)

        return None

    def _try_advance_time(self, dt: datetime) -> datetime | None:
        """尝试推进到当天匹配的时间"""
        if not self.hour_field.matches(dt.hour):
            next_hour = self.hour_field.get_next(dt.hour)
            if next_hour is None:
                return None
            if next_hour > dt.hour:
                return dt.replace(hour=next_hour, minute=0, second=0)
            return None

        if not self.minute_field.matches(dt.minute):
            next_minute = self.minute_field.get_next(dt.minute)
            if next_minute is None:
                return self._reset_hour(dt)
            if next_minute > dt.minute:
                return dt.replace(minute=next_minute, second=0)
            return self._reset_hour(dt)

        if not self.second_field.matches(dt.second):
            next_second = self.second_field.get_next(dt.second)
            if next_second is None:
                return self._reset_minute(dt)
            if next_second > dt.second:
                return dt.replace(second=next_second)
            return self._reset_minute(dt)

        return dt

    def _reset_hour(self, dt: datetime) -> datetime | None:
        """重置到下一个小时"""
        next_hour = self.hour_field.get_next(dt.hour + 1)
        if next_hour is not None and next_hour > dt.hour:
            return dt.replace(hour=next_hour, minute=0, second=0)
        return None

    def _reset_minute(self, dt: datetime) -> datetime | None:
        """重置到下一分钟"""
        next_minute = self.minute_field.get_next(dt.minute + 1)
        if next_minute is not None and next_minute > dt.minute:
            return dt.replace(minute=next_minute, second=0)
        return self._reset_hour(dt)

    def get_next_run_time(self, previous_time: datetime | None = None) -> TriggerResult:
        """获取下次运行时间"""
        now = datetime.now()

        if previous_time is None:
            start = now + timedelta(seconds=1)
        else:
            if previous_time.tzinfo is not None:
                previous_time = previous_time.replace(tzinfo=None)
            start = previous_time + timedelta(seconds=1)

        next_time = self._get_next_candidate(start)

        if next_time is None:
            return TriggerResult(next_run_time=None, should_run=False)

        return TriggerResult(next_run_time=next_time, should_run=False)

    def to_config(self) -> dict[str, Any]:
        """转换为配置字典"""
        config: dict[str, Any] = {}

        fields = [
            ("year", self.year_field),
            ("month", self.month_field),
            ("day", self.day_field),
            ("day_of_week", self.day_of_week_field),
            ("hour", self.hour_field),
            ("minute", self.minute_field),
            ("second", self.second_field),
        ]

        for name, field in fields:
            if field.values is not None:
                if len(field.values) == 1:
                    config[name] = next(iter(field.values))
                else:
                    config[name] = ",".join(map(str, sorted(field.values)))

        if self._start_date:
            config["start_date"] = self._start_date.isoformat()
        if self._end_date:
            config["end_date"] = self._end_date.isoformat()

        return config

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> Self:
        """从配置创建触发器"""
        return cls(
            year=config.get("year"),
            month=config.get("month"),
            day=config.get("day"),
            day_of_week=config.get("day_of_week"),
            hour=config.get("hour"),
            minute=config.get("minute"),
            second=config.get("second"),
            start_date=config.get("start_date"),
            end_date=config.get("end_date"),
            timezone=config.get("timezone"),
        )
