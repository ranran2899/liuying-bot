"""记忆类内置工具

用户记忆召回。
"""

from liuying.utils.log import logger

from ...agent.runtime.session_context import (
    get_current_persona_name,
    get_current_user_id,
)
from ...core.memory import memory_manager
from ..decorators import register_tool


@register_tool(
    name="recall_memory",
    description="召回与当前对话相关的历史记忆，适用于需要回顾过往互动的场景",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "查询文本",
            },
            "top_k": {
                "type": "integer",
                "description": "召回数量，默认5",
                "default": 5,
            },
        },
        "required": ["query"],
    },
    metadata={"tier_filter": ["working", "episodic", "semantic"]},
)
async def recall_memory(query: str, top_k: int = 5) -> str:
    """召回历史记忆

    参数:
        query: 查询文本
        top_k: 返回数量

    返回:
        str: 记忆摘要文本
    """
    user_id = get_current_user_id()
    if not user_id:
        return "缺少用户上下文，无法召回记忆"
    try:
        memories = await memory_manager.recall(
            user_id,
            query,
            top_k=top_k,
            persona_name=get_current_persona_name(),
        )
    except Exception as e:
        logger.warning(f"记忆召回失败: {e}", command="AI", e=e)
        return f"记忆召回失败: {type(e).__name__}"
    if not memories:
        return "未召回相关记忆"
    lines = []
    for mem in memories:
        lines.append(f"- {mem['summary']}")
    return "\n".join(lines)
