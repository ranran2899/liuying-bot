"""记忆类内置工具

用户记忆召回。
"""

from ....core.memory import memory_manager
from ...runtime.constants import (
    EVIDENCE_KIND_CONTEXT,
    INTENT_TAG_MEMORY,
    LATENCY_CLASS_FAST,
)
from ..decorators import register_tool


@register_tool(
    name="recall_memory",
    description="召回与当前对话相关的历史记忆，适用于需要回顾过往互动的场景",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "用户ID",
            },
            "query": {
                "type": "string",
                "description": "查询文本",
            },
            "top_k": {
                "type": "integer",
                "description": "召回数量，默认5",
                "default": 5,
            },
            "persona_name": {
                "type": "string",
                "description": "bot人格名（用于人设间记忆隔离）",
                "default": "default",
            },
        },
        "required": ["user_id", "query"],
    },
    intent_tags=[INTENT_TAG_MEMORY],
    latency_class=LATENCY_CLASS_FAST,
    evidence_kind=EVIDENCE_KIND_CONTEXT,
    metadata={"tier_filter": ["working", "episodic", "semantic"]},
)
async def recall_memory(
    user_id: str,
    query: str,
    top_k: int = 5,
    persona_name: str = "default",
) -> str:
    """召回历史记忆

    参数:
        user_id: 用户ID
        query: 查询文本
        top_k: 返回数量
        persona_name: bot人格名（用于人设间记忆隔离）

    返回:
        str: 记忆摘要文本
    """
    try:
        memories = await memory_manager.recall(
            user_id, query, top_k=top_k, persona_name=persona_name
        )
    except Exception as e:
        return f"记忆召回失败: {e}"
    if not memories:
        return "未召回相关记忆"
    lines = []
    for mem in memories:
        lines.append(f"- {mem['summary']}")
    return "\n".join(lines)
