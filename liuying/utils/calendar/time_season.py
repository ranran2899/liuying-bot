"""
时间季节判断工具类
"""
from bisect import bisect_right
from datetime import datetime
from typing import ClassVar

import pytz


class TimeSeason:
    """时间季节判断工具类"""

    DEFAULT_TIMEZONE = pytz.timezone("Asia/Shanghai")

    SEASON_BOUNDS: ClassVar[dict[int, list[tuple[int, str]]]] = {
        1: [(10, "暮春"), (20, "初夏"), (31, "仲夏")],
        2: [(31, "初春")],
        3: [(10, "初春"), (20, "仲春"), (31, "暮春")],
        4: [(10, "仲春"), (20, "暮春"), (31, "初夏")],
        5: [(10, "初夏"), (20, "仲夏"), (31, "暮夏")],
        6: [(10, "仲夏"), (20, "暮夏"), (31, "初秋")],
        7: [(10, "初秋"), (20, "仲秋"), (31, "暮秋")],
        8: [(10, "仲秋"), (20, "暮秋"), (31, "初冬")],
        9: [(10, "初冬"), (20, "仲冬"), (31, "暮冬")],
        10: [(10, "仲冬"), (20, "暮冬"), (31, "初春")],
        11: [(10, "初春"), (20, "仲春"), (31, "暮春")],
        12: [(10, "仲春"), (20, "暮春"), (31, "初夏")],
    }

    TIME_PERIOD_BOUNDS: ClassVar[list[int]] = [0, 5, 7, 9, 11, 13, 17, 19, 22, 24]
    TIME_PERIOD_NAMES: ClassVar[list[str]] = [
        "深夜", "凌晨", "清晨", "上午", "中午", "下午", "傍晚", "晚上", "深夜"
    ]

    @classmethod
    def get_season(cls, month: int, day: int) -> str:
        """根据月份和日期获取季节描述

        参数:
            month: 月份 (1-12)
            day: 日期 (1-31)

        返回:
            str: 季节描述
        """
        bounds = cls.SEASON_BOUNDS.get(month)
        if not bounds:
            return "未知"
        for bound, season in bounds:
            if day <= bound:
                return season
        return "未知"

    @classmethod
    def get_time_period(cls, hour: int, minute: int) -> str:
        """根据小时和分钟获取时间段描述

        参数:
            hour: 小时 (0-23)
            minute: 分钟 (0-59)

        返回:
            str: 时间段描述
        """
        index = bisect_right(cls.TIME_PERIOD_BOUNDS, hour) - 1
        return cls.TIME_PERIOD_NAMES[max(0, index)]

    @classmethod
    def parse_time_string(cls, time_str: str) -> tuple[int | None, int, int, int, int]:
        """解析时间字符串

        参数:
            time_str: 时间字符串，支持以下格式:
                     - "MM.DD HH:MM" 或 "MM.DD HH:MM:SS"
                     - "YYYY.MM.DD HH:MM" 或 "YYYY.MM.DD HH:MM:SS"

        返回:
            Tuple[Optional[int], int, int, int, int]: (year, month, day, hour, minute)
            year 可能为 None，表示未指定年份
        """
        parts = time_str.split()
        if len(parts) < 2:
            raise ValueError(
                f"无效的时间格式: '{time_str}'，"
                "期望格式为 'MM.DD HH:MM' 或 'YYYY.MM.DD HH:MM'"
            )

        date_part = parts[0]
        time_part = parts[1]

        date_parts = date_part.split(".")
        if len(date_parts) < 2:
            raise ValueError(
                f"无效的日期格式: '{date_part}'，"
                "期望格式为 'MM.DD' 或 'YYYY.MM.DD'"
            )

        if len(date_parts) == 3:
            year = int(date_parts[0])
            month = int(date_parts[1])
            day = int(date_parts[2])
        else:
            year = None
            month = int(date_parts[0])
            day = int(date_parts[1])

        time_parts = time_part.split(":")
        if len(time_parts) < 2:
            raise ValueError(f"无效的时间格式: '{time_part}'，期望格式为 'HH:MM'")

        hour = int(time_parts[0])
        minute = int(time_parts[1])

        return year, month, day, hour, minute

    @classmethod
    def get_time_description(cls, time_str: str) -> str:
        """获取时间的描述性文本

        参数:
            time_str: 时间字符串，支持以下格式:
                     - "MM.DD HH:MM" 或 "MM.DD HH:MM:SS"
                     - "YYYY.MM.DD HH:MM" 或 "YYYY.MM.DD HH:MM:SS"

        返回:
            str: 描述性文本，例如 "初春的下午"
        """
        year, month, day, hour, minute = cls.parse_time_string(time_str)
        season = cls.get_season(month, day)
        time_period = cls.get_time_period(hour, minute)
        return f"{season}的{time_period}"

    @classmethod
    def get_current_time_description(cls) -> str:
        """获取当前时间的描述性文本

        返回:
            str: 描述性文本，例如 "初春的下午"
        """
        now = datetime.now(cls.DEFAULT_TIMEZONE)
        season = cls.get_season(now.month, now.day)
        time_period = cls.get_time_period(now.hour, now.minute)
        return f"{season}的{time_period}"
