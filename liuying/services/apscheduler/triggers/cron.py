"""
Cron 表达式触发器

支持标准 cron 表达式的定时任务触发，采用字段级跳跃算法实现高性能计算。

标准 cron 默认值规则：
- 日期字段（year/month/day/day_of_week）未指定时匹配所有值
- 时间字段（hour/minute/second）未指定时默认为 0
"""

import bisect
import calendar
from datetime import datetime, timedelta
from typing import Any, Self

from ..constants import (
    CRON_DAY_MAX,
    CRON_DAY_MIN,
    CRON_DAY_OF_WEEK_MAX,
    CRON_DAY_OF_WEEK_MIN,
    CRON_HOUR_MAX,
    CRON_HOUR_MIN,
    CRON_MINUTE_MAX,
    CRON_MINUTE_MIN,
    CRON_MONTH_MAX,
    CRON_MONTH_MIN,
    CRON_SECOND_MAX,
    CRON_SECOND_MIN,
    CRON_YEAR_MAX,
    CRON_YEAR_MIN,
    SCHEDULER_MAX_CRON_ITERATIONS,
    SCHEDULER_MAX_TIME_ITERATIONS,
)
from .base import BaseTrigger, register_trigger


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
        elif isinstance(value, int):
            self.values = {value}
            self._sorted_values = [value]
        else:
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
                start = self.min_val if base == "*" else int(base)
                result.update(range(start, self.max_val + 1, step))
            elif "-" in part:
                start, end = part.split("-", 1)
                result.update(range(int(start), int(end) + 1))
            else:
                result.add(int(part))
        return result

    def matches(self, value: int) -> bool:
        """检查值是否匹配"""
        return self.values is None or value in self.values

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

    支持标准 cron 表达式格式，可指定年、月、日、星期、时、分、秒。

    默认值规则（与 APScheduler 标准一致）：
    - 日期字段未指定时匹配所有值（year/month/day/day_of_week → *）
    - 时间字段未指定时默认为 0（hour/minute/second → 0）

    采用字段级跳跃算法，避免逐秒/逐日遍历，大幅提升计算性能。
    """

    def __init__(
        self,
        year: int | str | None = None,
        month: int | str | None = None,
        day: int | str | None = None,
        day_of_week: int | str | None = None,
        hour: int | str | None = None,
        minute: int | str | None = None,
        second: int | str | None = None,
        start_date: datetime | str | None = None,
        end_date: datetime | str | None = None,
    ) -> None:
        super().__init__(start_date, end_date)

        self.year_field = CronField("year", CRON_YEAR_MIN, CRON_YEAR_MAX)
        self.month_field = CronField("month", CRON_MONTH_MIN, CRON_MONTH_MAX)
        self.day_field = CronField("day", CRON_DAY_MIN, CRON_DAY_MAX)
        self.day_of_week_field = CronField(
            "day_of_week", CRON_DAY_OF_WEEK_MIN, CRON_DAY_OF_WEEK_MAX
        )
        self.hour_field = CronField("hour", CRON_HOUR_MIN, CRON_HOUR_MAX)
        self.minute_field = CronField("minute", CRON_MINUTE_MIN, CRON_MINUTE_MAX)
        self.second_field = CronField("second", CRON_SECOND_MIN, CRON_SECOND_MAX)

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

        for _ in range(SCHEDULER_MAX_CRON_ITERATIONS):
            if dt.year > CRON_YEAR_MAX:
                return None
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
        """推进到下一个匹配月份的 1 日 0 时"""
        next_month = self.month_field.get_next_wrap(dt.month + 1)
        if next_month <= dt.month:
            next_year = self.year_field.get_next(dt.year + 1)
            if next_year is None:
                next_year = dt.year + 1
            return datetime(next_year, next_month, 1, 0, 0, 0)
        return dt.replace(month=next_month, day=1, hour=0, minute=0, second=0)

    def _first_of_next_month(self, dt: datetime) -> datetime:
        """推进到次月 1 日 0 时（不检查 month_field，由外层循环兜底）"""
        if dt.month == 12:
            return datetime(dt.year + 1, 1, 1)
        return datetime(dt.year, dt.month + 1, 1)

    def _next_day(self, dt: datetime) -> datetime:
        """推进到下一天 0 时"""
        next_dt = dt + timedelta(days=1)
        return next_dt.replace(hour=0, minute=0, second=0)

    def _try_advance_day(self, dt: datetime) -> datetime | None:
        """尝试推进到当天匹配的时间（day 不匹配时按字段值跳跃整月/整日）"""
        for _ in range(SCHEDULER_MAX_CRON_ITERATIONS):
            max_day = calendar.monthrange(dt.year, dt.month)[1]

            if not self.day_field.matches(dt.day):
                next_day = self.day_field.get_next(dt.day)
                if next_day is None or next_day > max_day:
                    dt = self._first_of_next_month(dt)
                else:
                    dt = dt.replace(day=next_day, hour=0, minute=0, second=0)
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
        """尝试推进到当天匹配的时间（时/分/秒逐级校验，低级字段推进后重新校验高级字段）"""
        for _ in range(SCHEDULER_MAX_TIME_ITERATIONS):
            if not self.hour_field.matches(dt.hour):
                next_hour = self.hour_field.get_next(dt.hour)
                if next_hour is None:
                    return None
                # 小时推进后 minute/second 归零，交由后续迭代重新校验
                dt = dt.replace(hour=next_hour, minute=0, second=0)
                continue

            if not self.minute_field.matches(dt.minute):
                next_minute = self.minute_field.get_next(dt.minute)
                if next_minute is None:
                    # 当前小时内已无匹配分钟，推进到下一个匹配小时
                    next_hour = self.hour_field.get_next(dt.hour + 1)
                    if next_hour is None:
                        return None
                    dt = dt.replace(hour=next_hour, minute=0, second=0)
                    continue
                dt = dt.replace(minute=next_minute, second=0)
                continue

            if not self.second_field.matches(dt.second):
                next_second = self.second_field.get_next(dt.second)
                if next_second is None:
                    # 当前分钟内已无匹配秒，推进到下一个匹配分钟
                    next_minute = self.minute_field.get_next(dt.minute + 1)
                    if next_minute is None:
                        next_hour = self.hour_field.get_next(dt.hour + 1)
                        if next_hour is None:
                            return None
                        dt = dt.replace(hour=next_hour, minute=0, second=0)
                    else:
                        dt = dt.replace(minute=next_minute, second=0)
                    continue
                return dt.replace(second=next_second)

            return dt

        return None

    def get_next_run_time(
        self, previous_time: datetime | None = None
    ) -> datetime | None:
        """获取下次运行时间，无下次执行时返回 None"""
        if previous_time is None:
            start = datetime.now() + timedelta(seconds=1)
        else:
            if previous_time.tzinfo is not None:
                previous_time = previous_time.replace(tzinfo=None)
            start = previous_time + timedelta(seconds=1)

        return self._get_next_candidate(start)

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
        )
