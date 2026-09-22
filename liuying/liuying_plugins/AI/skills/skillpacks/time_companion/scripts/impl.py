"""日期推算与时段陪伴实现

补齐 datetime_tool 之外的时间能力：日期差、倒计时、日期偏移，
以及当前时段的作息节律建议。
模型自行推算日期极易出错，本技能提供确定性结果。
"""

from datetime import date, datetime, timedelta
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from liuying.liuying_plugins.AI.tools import AgentTool

from . import rhythm

_DEFAULT_TZ = "Asia/Shanghai"
"""默认时区"""

_WEEKDAYS: tuple[str, ...] = (
    "周一",
    "周二",
    "周三",
    "周四",
    "周五",
    "周六",
    "周日",
)
"""星期中文名，索引对应 date.weekday()"""

_DATE_RE = re.compile(
    r"^(\d{4})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})\s*日?$"
)
"""日期字面量匹配，兼容 2026-01-02 / 2026年1月2日 / 2026/1/2"""

_MD_RE = re.compile(r"^(\d{1,2})\s*[-/月.]\s*(\d{1,2})\s*日?$")
"""缺省年份的月日匹配，按就近未来推断年份"""

_MAX_OFFSET_DAYS = 36500
"""日期偏移天数上限，约100年"""


def _now(timezone: str = _DEFAULT_TZ) -> datetime:
    """获取指定时区当前时间

    非法时区名回退到默认时区。

    参数:
        timezone: IANA 时区名

    返回:
        datetime: 带时区的当前时间
    """
    # 时区名由模型给出，非法值属预期输入错误，静默回退默认时区。
    try:
        tz = ZoneInfo(timezone or _DEFAULT_TZ)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo(_DEFAULT_TZ)
    return datetime.now(tz)


def parse_date(text: str, today: date) -> date | None:
    """解析日期文本

    支持绝对日期、缺省年份的月日、以及今天/明天/昨天等相对词。

    参数:
        text: 日期文本
        today: 当天日期，用于相对词与缺省年份推断

    返回:
        date | None: 解析结果，无法识别时返回 None
    """
    raw = (text or "").strip()
    if not raw:
        return None

    relative = {
        "今天": 0,
        "今日": 0,
        "明天": 1,
        "明日": 1,
        "后天": 2,
        "昨天": -1,
        "昨日": -1,
        "前天": -2,
    }
    if (delta := relative.get(raw)) is not None:
        return today + timedelta(days=delta)

    if match := _DATE_RE.match(raw):
        year, month, day = (int(g) for g in match.groups())
        return _safe_date(year, month, day)

    if match := _MD_RE.match(raw):
        month, day = (int(g) for g in match.groups())
        if (result := _safe_date(today.year, month, day)) is None:
            return None
        # 缺省年份时按就近未来解释，便于「还有几天到12月25日」类问法
        if result < today:
            result = _safe_date(today.year + 1, month, day)
        return result
    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    """构造日期并吞掉非法日期

    参数:
        year: 年
        month: 月
        day: 日

    返回:
        date | None: 合法日期，非法返回 None
    """
    # 2 月 30 日一类非法组合属预期输入错误，转为 None 交上层出提示。
    try:
        return date(year, month, day)
    except ValueError:
        return None


def date_diff(
    start: str, end: str, timezone: str = _DEFAULT_TZ
) -> str:
    """计算两个日期相差天数

    参数:
        start: 起始日期文本
        end: 结束日期文本
        timezone: 时区名

    返回:
        str: 天数差描述
    """
    today = _now(timezone).date()
    start_date = parse_date(start, today)
    end_date = parse_date(end, today)
    if start_date is None:
        return f"无法识别起始日期: {start}"
    if end_date is None:
        return f"无法识别结束日期: {end}"

    days = (end_date - start_date).days
    direction = "之后" if days >= 0 else "之前"
    return (
        f"{_fmt(start_date)} 到 {_fmt(end_date)} "
        f"相差 {abs(days)} 天（{direction}）"
    )


def days_until(target: str, timezone: str = _DEFAULT_TZ) -> str:
    """计算距目标日期还有多少天

    参数:
        target: 目标日期文本
        timezone: 时区名

    返回:
        str: 倒计时描述
    """
    today = _now(timezone).date()
    target_date = parse_date(target, today)
    if target_date is None:
        return f"无法识别目标日期: {target}"

    days = (target_date - today).days
    if days == 0:
        return f"{_fmt(target_date)} 就是今天"
    if days > 0:
        return f"距 {_fmt(target_date)} 还有 {days} 天"
    return f"{_fmt(target_date)} 已经过去 {abs(days)} 天"


def shift_date(
    base: str, days: int, timezone: str = _DEFAULT_TZ
) -> str:
    """按天数偏移日期

    参数:
        base: 基准日期文本
        days: 偏移天数，负数表示往前
        timezone: 时区名

    返回:
        str: 偏移结果描述
    """
    today = _now(timezone).date()
    base_date = parse_date(base, today)
    if base_date is None:
        return f"无法识别基准日期: {base}"
    if abs(days) > _MAX_OFFSET_DAYS:
        return f"偏移天数超出范围（最多{_MAX_OFFSET_DAYS}天）"

    result = base_date + timedelta(days=days)
    return f"{_fmt(base_date)} 偏移 {days} 天是 {_fmt(result)}"


def _fmt(value: date) -> str:
    """格式化日期为带星期的文本

    参数:
        value: 日期

    返回:
        str: 如 2026-08-12 周三
    """
    return f"{value.isoformat()} {_WEEKDAYS[value.weekday()]}"


def time_companion(
    timezone: str = _DEFAULT_TZ, mood: str = ""
) -> str:
    """给出当前时段的陪伴式描述与作息建议

    参数:
        timezone: 时区名
        mood: 情绪倾向，取 positive/negative/tired/neutral

    返回:
        str: 时段、招呼与作息建议
    """
    now = _now(timezone)
    return (
        f"{_fmt(now.date())}，{rhythm.advise(now, mood)}"
    )


def build_time_tools(runtime: Any) -> list[AgentTool]:
    """构建日期推算与时段陪伴工具集

    参数:
        runtime: SkillRuntime 实例，本技能不依赖其服务

    返回:
        list[AgentTool]: 工具列表
    """

    async def _diff(
        start: str, end: str, timezone: str = _DEFAULT_TZ
    ) -> str:
        """日期差handler

        参数:
            start: 起始日期
            end: 结束日期
            timezone: 时区名

        返回:
            str: 天数差描述
        """
        return date_diff(start, end, timezone)

    async def _until(
        target: str, timezone: str = _DEFAULT_TZ
    ) -> str:
        """倒计时handler

        参数:
            target: 目标日期
            timezone: 时区名

        返回:
            str: 倒计时描述
        """
        return days_until(target, timezone)

    async def _shift(
        base: str, days: int, timezone: str = _DEFAULT_TZ
    ) -> str:
        """日期偏移handler

        参数:
            base: 基准日期
            days: 偏移天数
            timezone: 时区名

        返回:
            str: 偏移结果
        """
        return shift_date(base, days, timezone)

    async def _companion(
        timezone: str = _DEFAULT_TZ, mood: str = ""
    ) -> str:
        """时段陪伴handler

        参数:
            timezone: 时区名
            mood: 情绪倾向

        返回:
            str: 时段与作息建议
        """
        return time_companion(timezone, mood)

    tz_schema = {
        "type": "string",
        "description": f"时区名，默认{_DEFAULT_TZ}",
    }
    date_desc = "日期，支持 2026-01-02 / 1月2日 / 今天 / 明天"

    return [
        AgentTool(
            name="date_diff",
            description="计算两个日期相差的天数",
            parameters={
                "type": "object",
                "properties": {
                    "start": {
                        "type": "string",
                        "description": f"起始{date_desc}",
                    },
                    "end": {
                        "type": "string",
                        "description": f"结束{date_desc}",
                    },
                    "timezone": tz_schema,
                },
                "required": ["start", "end"],
            },
            func=_diff,
        ),
        AgentTool(
            name="days_until",
            description="计算距某个日期还剩多少天，用于倒计时与纪念日",
            parameters={
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": f"目标{date_desc}",
                    },
                    "timezone": tz_schema,
                },
                "required": ["target"],
            },
            func=_until,
        ),
        AgentTool(
            name="shift_date",
            description="在给定日期上加减天数，得到目标日期与星期",
            parameters={
                "type": "object",
                "properties": {
                    "base": {
                        "type": "string",
                        "description": f"基准{date_desc}",
                    },
                    "days": {
                        "type": "integer",
                        "description": "偏移天数，负数表示往前",
                    },
                    "timezone": tz_schema,
                },
                "required": ["base", "days"],
            },
            func=_shift,
        ),
        AgentTool(
            name="time_companion",
            description=(
                "查当前时段与对应的作息建议。用户提到熬夜、"
                "困、还没睡、刚起床、要不要休息这类作息话题，"
                "或需要按时段调整招呼语时用本工具。"
                "只想知道几点用 get_current_time"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "timezone": tz_schema,
                    "mood": {
                        "type": "string",
                        "enum": [
                            "positive",
                            "negative",
                            "tired",
                            "neutral",
                        ],
                        "description": "对方当前的情绪倾向",
                    },
                },
                "required": [],
            },
            func=_companion,
        ),
    ]
