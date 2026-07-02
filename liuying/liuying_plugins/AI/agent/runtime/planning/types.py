"""回合规划数据类型

定义 TurnPlan 数据结构，供规划器、执行器和响应器消费。
"""

from dataclasses import dataclass, field
from typing import Any

from ..constants import (
    DEFAULT_AGENT_MAX_STEPS,
    OUTPUT_MODE_CHAT_SHORT,
    TURN_ACTION_ASK_CLARIFY,
    TURN_ACTION_REPLY,
    TURN_ACTION_SILENCE,
)


@dataclass(slots=True)
class TurnPlan:
    """回合规划

    描述本回合的决策结果，由规划器生成，由执行器和响应器消费。

    Attributes:
        action: 回合动作（reply/silence/ask_clarify）
        output_mode: 输出模式
        intent_tags: 意图标签列表
        need_tool: 是否需要工具调用
        tool_candidates: 候选工具名列表
        tool_name: 选定工具名（单工具调用时）
        tool_args: 工具参数
        need_memory: 是否需要记忆召回
        memory_query: 记忆查询文本
        need_vision: 是否需要视觉理解
        vision_hint: 视觉提示
        need_research: 是否需要多步研究
        ambiguity_level: 模糊度（0-1）
        max_steps: 最大步数
        reason: 决策理由
        user_id: 当前用户ID（执行器注入上下文用）
        group_id: 当前群组ID（执行器注入上下文用）
        user_message: 原始用户消息（执行器兜底用）
        persona_name: 当前bot人格名（用于记忆/情绪隔离）
    """

    action: str = TURN_ACTION_REPLY
    output_mode: str = OUTPUT_MODE_CHAT_SHORT
    intent_tags: list[str] = field(default_factory=list)
    need_tool: bool = False
    tool_candidates: list[str] = field(default_factory=list)
    tool_name: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)
    need_memory: bool = False
    memory_query: str = ""
    need_vision: bool = False
    vision_hint: str = ""
    need_research: bool = False
    ambiguity_level: float = 0.0
    max_steps: int = DEFAULT_AGENT_MAX_STEPS
    reason: str = ""
    user_id: str = ""
    group_id: str | None = None
    user_message: str = ""
    persona_name: str = "default"

    @property
    def is_silence(self) -> bool:
        """是否静默"""
        return self.action == TURN_ACTION_SILENCE

    @property
    def is_clarify(self) -> bool:
        """是否请求澄清"""
        return self.action == TURN_ACTION_ASK_CLARIFY

    def to_dict(self) -> dict[str, Any]:
        """转换为字典

        返回:
            dict: 规划字典
        """
        return {
            "action": self.action,
            "output_mode": self.output_mode,
            "intent_tags": list(self.intent_tags),
            "need_tool": self.need_tool,
            "tool_candidates": list(self.tool_candidates),
            "tool_name": self.tool_name,
            "tool_args": dict(self.tool_args),
            "need_memory": self.need_memory,
            "memory_query": self.memory_query,
            "need_vision": self.need_vision,
            "vision_hint": self.vision_hint,
            "need_research": self.need_research,
            "ambiguity_level": self.ambiguity_level,
            "max_steps": self.max_steps,
            "reason": self.reason,
            "user_id": self.user_id,
            "group_id": self.group_id,
            "user_message": self.user_message,
            "persona_name": self.persona_name,
        }
