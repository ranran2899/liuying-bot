"""日期时间查询实现

当前时间能力的唯一实现：按时区返回格式化时间，并附带本地时段与活动状态。
替代原内置工具 get_datetime，统一收敛到技能包。
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from liuying.liuying_plugins.AI.core.context import context_manager
from liuying.liuying_plugins.AI.tools import AgentTool

_DEFAULT_TZ = "Asia/Shanghai"
"""默认时区"""

_WEEKDAYS = (
    "周一", "周二", "周三", "周四", "周五", "周六", "周日"
)
"""星期中文映射"""


def get_current_datetime_info(
    timezone: str = "Asia/Shanghai",
) -> str:
    """获取当前日期时间

    根据指定时区返回格式化的当前时间，并附带本地时段与活动状态描述。

    参数:
        timezone: 时区名（IANA时区标识），默认 Asia/Shanghai

    返回:
        str: 格式化的当前时间描述
    """
    tz_name = (timezone or _DEFAULT_TZ).strip()
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        return (
            f"时区 '{tz_name}' 无效，请使用有效的 IANA 时区标识"
            f"（如 Asia/Shanghai）"
        )
    now = datetime.now(tz)
    weekday = _WEEKDAYS[now.weekday()]
    period = context_manager.get_current_time_period()
    activity = context_manager.get_activity_status()
    return (
        f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')} "
        f"{weekday}（时区: {tz_name}）\n"
        f"时段: {period}\n{activity}"
    )


def build_datetime_tool(runtime: Any) -> AgentTool:
    """构建日期时间查询工具

    参数:
        runtime: SkillRuntime 实例（本工具不依赖runtime服务）

    返回:
        AgentTool: 日期时间查询工具
    """
    # datetime_tool 不依赖 runtime 服务，使用标准库直接实现

    async def _handler(timezone: str = "Asia/Shanghai") -> str:
        """日期时间查询handler

        参数:
            timezone: 时区名

        返回:
            str: 当前时间描述
        """
        return get_current_datetime_info(timezone)

    return AgentTool(
        name="get_current_time",
        description=(
            "获取当前日期时间（支持时区），并附带当前时段与活动状态。"
            "用户问现在几点、今天周几、现在是什么时段时用本工具"
        ),
        parameters={
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "时区名，默认 Asia/Shanghai",
                    "default": "Asia/Shanghai",
                },
            },
            "required": [],
        },
        func=_handler,
    )
