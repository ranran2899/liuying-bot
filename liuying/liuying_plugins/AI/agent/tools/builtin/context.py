"""上下文类内置工具

好感度查询 + 当前时间获取。
"""

from datetime import datetime

from liuying.utils.user.favor import UserFavor

from ....core.context import context_manager
from ...runtime.constants import (
    EVIDENCE_KIND_CONTEXT,
    INTENT_TAG_LOCAL,
    LATENCY_CLASS_FAST,
)
from ..decorators import register_tool


@register_tool(
    name="get_favor",
    description="查询用户好感度，适用于判断关系亲密度调整回复语气的场景",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "用户ID",
            },
        },
        "required": ["user_id"],
    },
    intent_tags=[INTENT_TAG_LOCAL],
    latency_class=LATENCY_CLASS_FAST,
    evidence_kind=EVIDENCE_KIND_CONTEXT,
)
async def get_favor(user_id: str) -> str:
    """查询用户好感度

    参数:
        user_id: 用户ID

    返回:
        str: 好感度信息文本
    """
    try:
        info = await UserFavor.get_favor_info(user_id)
        favor_value = info.get("favor_value", 0)
        favor_level = info.get("favor_level", "陌生")
        return f"好感度: {favor_value} ({favor_level})"
    except Exception as e:
        return f"查询失败: {e}"


@register_tool(
    name="get_datetime",
    description="获取当前日期时间和活动状态，适用于时间相关查询",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
    intent_tags=[INTENT_TAG_LOCAL],
    latency_class=LATENCY_CLASS_FAST,
    evidence_kind=EVIDENCE_KIND_CONTEXT,
)
async def get_datetime() -> str:
    """获取当前日期时间

    返回:
        str: 当前时间描述
    """
    period = context_manager.get_current_time_period()
    activity = context_manager.get_activity_status()

    now = datetime.now()
    weekday = [
        "周一", "周二", "周三", "周四", "周五", "周六", "周日"
    ][now.weekday()]
    return (
        f"当前时间: {now.strftime('%Y-%m-%d %H:%M')} "
        f"{weekday}（{period}）\n{activity}"
    )
