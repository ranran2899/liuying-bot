"""日期时间工具

提供带时区的当前时间查询能力。
"""

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_DEFAULT_TZ = "Asia/Shanghai"
"""默认时区"""

_WEEKDAYS = (
    "周一", "周二", "周三", "周四", "周五", "周六", "周日"
)
"""星期中文映射"""


def get_current_time(timezone: str = "Asia/Shanghai") -> str:
    """获取当前日期时间

    根据指定时区返回格式化的当前时间字符串。

    参数:
        timezone: 时区名（IANA时区标识），默认 Asia/Shanghai

    返回:
        str: 格式化的当前时间描述
    """
    tz_name = (timezone or _DEFAULT_TZ).strip()
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo(_DEFAULT_TZ)
        tz_name = f"{tz_name}(无效，回退{_DEFAULT_TZ})"

    now = datetime.now(tz)
    weekday = _WEEKDAYS[now.weekday()]
    return (
        f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')} "
        f"{weekday}（时区: {tz_name}）"
    )
