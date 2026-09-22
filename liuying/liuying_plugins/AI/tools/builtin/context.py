"""上下文类内置工具

好感度查询。当前时间能力已收敛到 datetime_tool 技能包（get_current_time）。
"""

from liuying.utils.user.favor import UserFavor

from ...agent.runtime.session_context import get_current_user_id
from ..decorators import register_tool


@register_tool(
    name="get_favor",
    description="查询当前用户好感度，适用于判断关系亲密度调整回复语气的场景",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
async def get_favor() -> str:
    """查询当前用户好感度

    返回:
        str: 好感度信息文本
    """
    user_id = get_current_user_id()
    if not user_id:
        return "缺少用户上下文，无法查询好感度"
    info = await UserFavor.get_favor_info(user_id)
    favor_value = info.get("favor_value", 0)
    favor_level = info.get("favor_level", "陌生")
    return f"好感度: {favor_value} ({favor_level})"
