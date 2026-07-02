from datetime import datetime

import pytz


class TimeSeason:
    """时间季节判断工具类"""

    DEFAULT_TIMEZONE = pytz.timezone("Asia/Shanghai")

    @classmethod
    def get_season(cls, month: int, day: int) -> str:
        """根据月份和日期获取季节描述
        
        参数:
            month: 月份 (1-12)
            day: 日期 (1-31)
            
        返回:
            str: 季节描述
        """
        if month == 2:
            return "初春"
        elif month == 3:
            if day < 10:
                return "初春"
            elif day < 20:
                return "仲春"
            else:
                return "暮春"
        elif month == 4:
            if day < 10:
                return "仲春"
            elif day < 20:
                return "暮春"
            else:
                return "初夏"
        elif month == 5:
            if day < 10:
                return "初夏"
            elif day < 20:
                return "仲夏"
            else:
                return "暮夏"
        elif month == 6:
            if day < 10:
                return "仲夏"
            elif day < 20:
                return "暮夏"
            else:
                return "初秋"
        elif month == 7:
            if day < 10:
                return "初秋"
            elif day < 20:
                return "仲秋"
            else:
                return "暮秋"
        elif month == 8:
            if day < 10:
                return "仲秋"
            elif day < 20:
                return "暮秋"
            else:
                return "初冬"
        elif month == 9:
            if day < 10:
                return "初冬"
            elif day < 20:
                return "仲冬"
            else:
                return "暮冬"
        elif month == 10:
            if day < 10:
                return "仲冬"
            elif day < 20:
                return "暮冬"
            else:
                return "初春"
        elif month == 11:
            if day < 10:
                return "初春"
            elif day < 20:
                return "仲春"
            else:
                return "暮春"
        elif month == 12:
            if day < 10:
                return "仲春"
            elif day < 20:
                return "暮春"
            else:
                return "初夏"
        elif month == 1:
            if day < 10:
                return "暮春"
            elif day < 20:
                return "初夏"
            else:
                return "仲夏"
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
        if hour >= 0 and hour < 5:
            return "深夜"
        elif hour >= 5 and hour < 7:
            return "凌晨"
        elif hour >= 7 and hour < 9:
            return "清晨"
        elif hour >= 9 and hour < 11:
            return "上午"
        elif hour >= 11 and hour < 13:
            return "中午"
        elif hour >= 13 and hour < 17:
            return "下午"
        elif hour >= 17 and hour < 19:
            return "傍晚"
        elif hour >= 19 and hour < 22:
            return "晚上"
        else:
            return "深夜"

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
            raise ValueError(f"无效的时间格式: '{time_str}'，期望格式为 'MM.DD HH:MM' 或 'YYYY.MM.DD HH:MM'")

        date_part = parts[0]
        time_part = parts[1]

        date_parts = date_part.split(".")
        if len(date_parts) < 2:
            raise ValueError(f"无效的日期格式: '{date_part}'，期望格式为 'MM.DD' 或 'YYYY.MM.DD'")

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
