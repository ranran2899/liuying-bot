"""时间上下文

时间感知：工作日/周末/假期/时段判断，节日检测，
生成时间上下文提示文本。
"""

from datetime import date, datetime
from typing import ClassVar

from liuying.utils.log import logger

__all__ = ["TimeContext", "time_context"]


class TimeContext:
    """时间上下文

    时间感知与节日检测，生成时间上下文提示文本，
    为AI对话提供时间场景信息。
    """

    _TIME_PERIODS: ClassVar[list[tuple[int, int, str]]] = [
        (6, 12, "早晨"),
        (12, 18, "下午"),
        (18, 23, "晚上"),
        (0, 6, "深夜"),
        (23, 24, "深夜"),
    ]
    """时段定义表"""

    _WEEKDAY_NAMES: ClassVar[list[str]] = [
        "周一", "周二", "周三", "周四", "周五", "周六", "周日"
    ]
    """星期名称"""

    _SOLAR_FESTIVALS: ClassVar[dict[str, str]] = {
        "01-01": "元旦",
        "02-14": "情人节",
        "03-08": "妇女节",
        "03-12": "植树节",
        "05-01": "劳动节",
        "05-04": "青年节",
        "06-01": "儿童节",
        "07-01": "建党节",
        "08-01": "建军节",
        "09-10": "教师节",
        "10-01": "国庆节",
        "12-25": "圣诞节",
    }
    """公历节日映射"""

    _LUNAR_FESTIVALS: ClassVar[dict[str, str]] = {
        "2024-02-10": "春节",
        "2024-04-04": "清明节",
        "2024-06-10": "端午节",
        "2024-09-17": "中秋节",
        "2025-01-29": "春节",
        "2025-04-04": "清明节",
        "2025-05-31": "端午节",
        "2025-10-06": "中秋节",
        "2026-02-17": "春节",
        "2026-04-05": "清明节",
        "2026-06-19": "端午节",
        "2026-09-25": "中秋节",
        "2027-02-06": "春节",
        "2027-04-05": "清明节",
        "2027-06-20": "端午节",
        "2027-09-15": "中秋节",
        "2028-01-26": "春节",
        "2028-04-04": "清明节",
        "2028-06-09": "端午节",
        "2028-10-03": "中秋节",
        "2029-02-13": "春节",
        "2029-04-04": "清明节",
        "2029-05-28": "端午节",
        "2029-09-22": "中秋节",
        "2030-02-03": "春节",
        "2030-04-05": "清明节",
        "2030-06-13": "端午节",
        "2030-09-12": "中秋节",
    }
    """农历节日映射（预置2024-2030）"""

    def get_context(self) -> str:
        """生成时间上下文提示文本

        返回:
            str: 时间上下文提示，用于注入系统提示词
        """
        now = datetime.now()
        weekday = self._WEEKDAY_NAMES[now.weekday()]
        time_str = now.strftime("%H:%M")
        period = self.get_period()
        day_type = self._get_day_type()
        festival = self._get_festival(now.date())

        lines = [
            "[当前时间上下文]",
            f"时间: {weekday} {now.strftime('%Y-%m-%d')} {time_str}",
            f"时段: {period}",
            f"日期类型: {day_type}",
        ]
        if festival:
            lines.append(f"节日: {festival}")
        return "\n".join(lines)

    def get_period(self) -> str:
        """获取当前时段

        返回:
            str: 时段名称（早晨/下午/晚上/深夜）
        """
        hour = datetime.now().hour
        for start, end, name in self._TIME_PERIODS:
            if start <= hour < end:
                return name
        return "深夜"

    def is_holiday(self) -> bool:
        """判断今天是否为休息日

        周末或法定节假日返回True。

        返回:
            bool: 是否为休息日
        """
        today = date.today()
        if today.weekday() >= 5:
            return True
        if self._get_festival(today):
            return True
        return False

    def _get_day_type(self) -> str:
        """获取日期类型描述

        返回:
            str: 工作日/周末/节假日
        """
        today = date.today()
        festival = self._get_festival(today)
        if festival:
            return f"节假日（{festival}）"
        if today.weekday() >= 5:
            return "周末"
        return "工作日"

    def _get_festival(self, target: date) -> str:
        """获取指定日期的节日名称

        参数:
            target: 目标日期

        返回:
            str: 节日名称，无则返回空串
        """
        try:
            solar_key = target.strftime("%m-%d")
            solar = self._SOLAR_FESTIVALS.get(solar_key, "")
            if solar:
                return solar
            lunar = self._LUNAR_FESTIVALS.get(target.isoformat(), "")
            return lunar
        except Exception as e:
            logger.debug(
                f"节日检测失败: {e}", command="AI", e=e
            )
            return ""


time_context = TimeContext()
"""时间上下文单例"""
