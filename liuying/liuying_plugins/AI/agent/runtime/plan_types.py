"""回合规划数据类型

定义 TurnPlan 数据结构及其解析/校验/降级逻辑。
参考 nonebot_plugin_personification 的 planner.py 设计，
增强规划字段：length_bounds/confidence/message_target/session_goal，
并内嵌 metadata_fallback 降级与 payload 解析。
"""

from dataclasses import dataclass, field
from typing import Any

from ...core.tools.json_utils import extract_json_payload
from .constants import (
    DEFAULT_AGENT_MAX_STEPS,
    OUTPUT_MODE_CHAT_SHORT,
    TURN_ACTION_ASK_CLARIFY,
    TURN_ACTION_REPLY,
    TURN_ACTION_SILENCE,
)

# ===== 枚举白名单 =====
ALLOWED_REPLY_ACTIONS: set[str] = {
    TURN_ACTION_REPLY,
    TURN_ACTION_SILENCE,
    TURN_ACTION_ASK_CLARIFY,
}
ALLOWED_OUTPUT_MODES: set[str] = {
    "chat_short",
    "chat_answer",
    "structured_help",
    "source_summary",
    "silence",
}
ALLOWED_AMBIGUITY_LEVELS: set[str] = {"low", "medium", "high"}
ALLOWED_MESSAGE_TARGETS: set[str] = {
    "bot",
    "someone_else",
    "broadcast",
    "uncertain",
}

# ===== 输出模式字数约束 =====
OUTPUT_MODE_LENGTHS: dict[str, tuple[int, int]] = {
    "chat_short": (8, 40),
    "chat_answer": (30, 120),
    "structured_help": (80, 300),
    "source_summary": (80, 240),
    "silence": (0, 0),
}
"""输出模式对应字数范围 (min, max)，响应器据此硬约束回复长度"""


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
        ambiguity_level: 模糊度（low/medium/high）
        max_steps: 最大步数
        reason: 决策理由
        user_id: 当前用户ID（执行器注入上下文用）
        group_id: 当前群组ID（执行器注入上下文用）
        user_message: 原始用户消息（执行器兜底用）
        persona_name: 当前bot人格名
        semantic_frame: 语义帧字典
        confidence: 决策置信度（0-1）
        message_target: 消息目标（bot/someone_else/broadcast/uncertain）
        session_goal: 本回合会话目标（一句短中文）
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
    ambiguity_level: str = "low"
    max_steps: int = DEFAULT_AGENT_MAX_STEPS
    reason: str = ""
    user_id: str = ""
    group_id: str | None = None
    user_message: str = ""
    persona_name: str = "default"
    semantic_frame: dict[str, Any] | None = None
    confidence: float = 0.0
    message_target: str = "uncertain"
    session_goal: str = ""
    query_candidates: list[str] = field(default_factory=list)

    @property
    def is_silence(self) -> bool:
        """是否静默"""
        return self.action == TURN_ACTION_SILENCE

    @property
    def is_clarify(self) -> bool:
        """是否请求澄清"""
        return self.action == TURN_ACTION_ASK_CLARIFY

    @property
    def length_bounds(self) -> tuple[int, int]:
        """输出模式对应的字数范围 (min, max)

        响应器据此硬约束回复长度，避免过长回复消耗token。
        """
        return OUTPUT_MODE_LENGTHS.get(
            self.output_mode, OUTPUT_MODE_LENGTHS["chat_short"]
        )

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
            "semantic_frame": dict(self.semantic_frame)
            if self.semantic_frame
            else None,
            "confidence": self.confidence,
            "message_target": self.message_target,
            "session_goal": self.session_goal,
            "query_candidates": list(self.query_candidates),
        }


# ===== 工具函数 =====


def _enum_value(value: Any, allowed: set[str], default: str) -> str:
    """枚举值校验

    参数:
        value: 原始值
        allowed: 允许值集合
        default: 默认值

    返回:
        str: 校验后的枚举值
    """
    text = str(value or "").strip()
    return text if text in allowed else default


def _coerce_float(value: Any, default: float = 0.0) -> float:
    """安全转浮点数

    参数:
        value: 原始值
        default: 默认值

    返回:
        float: 转换后的浮点数
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_bool(value: Any, default: bool = False) -> bool:
    """安全转布尔值

    参数:
        value: 原始值
        default: 默认值

    返回:
        bool: 转换后的布尔值
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "on"}:
            return True
        if lowered in {"false", "0", "no", "n", "off"}:
            return False
    if value is None:
        return default
    return bool(value)


def _coerce_ambiguity(value: Any) -> str:
    """模糊度兼容转换：支持数值(0-1)和字符串(low/medium/high)

    参数:
        value: 原始值（float 或 str）

    返回:
        str: low/medium/high
    """
    match value:
        case int() | float() if not isinstance(value, bool):
            if value >= 0.7:
                return "high"
            if value >= 0.3:
                return "medium"
            return "low"
        case _:
            return _enum_value(value, ALLOWED_AMBIGUITY_LEVELS, "low")


def parse_turn_plan_payload(payload: Any) -> TurnPlan | None:
    """从LLM返回的payload解析TurnPlan

    对枚举字段做白名单校验，非法值降级为默认。

    参数:
        payload: LLM返回的字典

    返回:
        TurnPlan | None: 解析失败返回None
    """
    if not isinstance(payload, dict):
        return None
    action = _enum_value(
        payload.get("action"), ALLOWED_REPLY_ACTIONS, ""
    )
    if not action:
        return None
    output_mode = _enum_value(
        payload.get("output_mode"), ALLOWED_OUTPUT_MODES, "chat_short"
    )
    ambiguity = _coerce_ambiguity(payload.get("ambiguity_level"))
    confidence = max(
        0.0, min(1.0, _coerce_float(payload.get("confidence"), 0.0))
    )
    message_target = _enum_value(
        payload.get("message_target"),
        ALLOWED_MESSAGE_TARGETS,
        "uncertain",
    )
    need_tool = _coerce_bool(payload.get("need_tool"), False)
    need_memory = _coerce_bool(payload.get("need_memory"), False)
    need_vision = _coerce_bool(payload.get("need_vision"), False)
    need_research = _coerce_bool(payload.get("need_research"), False)
    tool_candidates_raw = payload.get("tool_candidates", [])
    if isinstance(tool_candidates_raw, str):
        tool_candidates = [tool_candidates_raw]
    elif isinstance(tool_candidates_raw, list):
        tool_candidates = [
            str(t).strip() for t in tool_candidates_raw if t
        ]
    else:
        tool_candidates = []
    intent_tags_raw = payload.get("intent_tags", [])
    if isinstance(intent_tags_raw, str):
        intent_tags = [intent_tags_raw]
    elif isinstance(intent_tags_raw, list):
        intent_tags = [str(t).strip() for t in intent_tags_raw if t]
    else:
        intent_tags = []
    tool_args_raw = payload.get("tool_args", {})
    tool_args = dict(tool_args_raw) if isinstance(tool_args_raw, dict) else {}
    return TurnPlan(
        action=action,
        output_mode=output_mode,
        intent_tags=intent_tags,
        need_tool=need_tool,
        tool_candidates=tool_candidates,
        tool_name=str(payload.get("tool_name", "") or "").strip(),
        tool_args=tool_args,
        need_memory=need_memory,
        memory_query=str(payload.get("memory_query", "") or "").strip(),
        need_vision=need_vision,
        vision_hint=str(payload.get("vision_hint", "") or "").strip(),
        need_research=need_research,
        ambiguity_level=ambiguity,
        confidence=confidence,
        reason=str(payload.get("reason", "") or "").strip()[:80],
        message_target=message_target,
        session_goal=str(
            payload.get("session_goal", "") or ""
        ).strip()[:80],
    )


def metadata_fallback_turn_plan(
    *,
    is_group: bool = False,
    is_random_chat: bool = False,
    is_direct_mention: bool = False,
    has_images: bool = False,
    message_target: str = "",
) -> TurnPlan:
    """无LLM时的元数据兜底规划

    基于场景元数据（群聊/私聊/随机插话/@bot/图片）快速决策，
    避免LLM调用，作为规划器降级路径。

    参数:
        is_group: 是否群聊
        is_random_chat: 是否随机插话（未被@）
        is_direct_mention: 是否直呼/@bot
        has_images: 是否有图片
        message_target: 代码侧推断的消息目标

    返回:
        TurnPlan: 兜底规划
    """
    target = str(message_target or "").strip()
    # 群聊随机插话且未@bot时静默，避免误插话
    if is_group and is_random_chat and not is_direct_mention:
        if target not in {"bot", "broadcast"}:
            return TurnPlan(
                action=TURN_ACTION_SILENCE,
                output_mode="silence",
                ambiguity_level="high",
                confidence=0.18,
                reason="metadata_fallback_random_group",
                message_target="uncertain",
                session_goal="避免误插话",
                need_vision=has_images,
                vision_hint="summary" if has_images else "",
            )
    # 默认回复
    return TurnPlan(
        action=TURN_ACTION_REPLY,
        output_mode=OUTPUT_MODE_CHAT_SHORT,
        need_memory=is_group,
        ambiguity_level="low",
        confidence=0.18,
        reason="metadata_fallback",
        message_target=(
            "bot"
            if (not is_group or is_direct_mention or target == "bot")
            else "broadcast"
        ),
        session_goal="自然回应当前轮次",
        need_vision=has_images,
        vision_hint="summary" if has_images else "",
    )


__all__ = [
    "ALLOWED_AMBIGUITY_LEVELS",
    "ALLOWED_MESSAGE_TARGETS",
    "ALLOWED_OUTPUT_MODES",
    "ALLOWED_REPLY_ACTIONS",
    "OUTPUT_MODE_LENGTHS",
    "TurnPlan",
    "extract_json_payload",
    "metadata_fallback_turn_plan",
    "parse_turn_plan_payload",
]
