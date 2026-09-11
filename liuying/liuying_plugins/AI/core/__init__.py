"""核心服务层

提供LLM调用封装、记忆系统、上下文管理、运行时开关、
环境感知、消息目标推断、社交智能框架与回复回合追踪。
情绪/画像/门控/主动学习等辅助LLM分析模块已迁移至
agent/（按角色前缀命名），本包不再re-export。

分类标准：独立功能域（含多文件或强内聚状态）组织为子包；
跨域共用的单文件行为模块（chat_intent/peer_awareness等）
保留为顶层模块，通过本模块统一 re-export。
"""

from .chat_intent import (
    SemanticFrameInferrer,
    TurnSemanticFrame,
    semantic_frame_inferrer,
)
from .context import ContextManager, context_manager
from .llm import LLMHelper, llm_helper
from .memory import MemoryManager, memory_manager
from .peer_awareness import PeerAwareness, peer_awareness
from .reply_turn_trace import (
    ReplyTurnTrace,
    reply_turn_trace,
)
from .social import (
    SocialContext,
    SocialQuota,
    SocialTrigger,
    SocialTriggerRegistry,
    social_quota,
    social_trigger_registry,
)
from .target_inference import (
    MessageTarget,
    TargetInference,
    target_inference,
)

__all__ = [
    "ContextManager",
    "LLMHelper",
    "MemoryManager",
    "MessageTarget",
    "PeerAwareness",
    "ReplyTurnTrace",
    "SemanticFrameInferrer",
    "SocialContext",
    "SocialQuota",
    "SocialTrigger",
    "SocialTriggerRegistry",
    "TargetInference",
    "TurnSemanticFrame",
    "context_manager",
    "llm_helper",
    "memory_manager",
    "peer_awareness",
    "reply_turn_trace",
    "semantic_frame_inferrer",
    "social_quota",
    "social_trigger_registry",
    "target_inference",
]
