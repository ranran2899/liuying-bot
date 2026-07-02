"""Agent运行时模块

提供规划-执行-响应三层分离的Agent架构。
"""

from .catalog import ToolCatalog, ToolCategory
from .constants import (
    DEFAULT_AGENT_MAX_STEPS,
    DEFAULT_TIME_BUDGET,
    EVIDENCE_KIND_CONTEXT,
    EVIDENCE_KIND_TOOL,
    LATENCY_CLASS_FAST,
    LATENCY_CLASS_NETWORK,
    LATENCY_CLASS_SLOW,
    OUTPUT_MODE_CHAT_ANSWER,
    OUTPUT_MODE_CHAT_SHORT,
    OUTPUT_MODE_SILENCE,
    OUTPUT_MODE_SOURCE_SUMMARY,
    OUTPUT_MODE_STRUCTURED_HELP,
    TURN_ACTION_ASK_CLARIFY,
    TURN_ACTION_REPLY,
    TURN_ACTION_SILENCE,
)
from .execution import EvidenceComposer, ToolExecutor
from .planning import TurnPlan, TurnPlanner
from .response import PersonaResponder, PersonaResponse

__all__ = [
    "DEFAULT_AGENT_MAX_STEPS",
    "DEFAULT_TIME_BUDGET",
    "EVIDENCE_KIND_CONTEXT",
    "EVIDENCE_KIND_TOOL",
    "LATENCY_CLASS_FAST",
    "LATENCY_CLASS_NETWORK",
    "LATENCY_CLASS_SLOW",
    "OUTPUT_MODE_CHAT_ANSWER",
    "OUTPUT_MODE_CHAT_SHORT",
    "OUTPUT_MODE_SILENCE",
    "OUTPUT_MODE_SOURCE_SUMMARY",
    "OUTPUT_MODE_STRUCTURED_HELP",
    "TURN_ACTION_ASK_CLARIFY",
    "TURN_ACTION_REPLY",
    "TURN_ACTION_SILENCE",
    "EvidenceComposer",
    "PersonaResponder",
    "PersonaResponse",
    "ToolCatalog",
    "ToolCategory",
    "ToolExecutor",
    "TurnPlan",
    "TurnPlanner",
]
