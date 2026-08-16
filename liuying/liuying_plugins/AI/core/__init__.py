"""核心服务层

提供LLM调用封装、人格管理、记忆系统、情绪状态、上下文管理、
画像服务、运行时开关、环境感知、主动学习、消息目标推断、
社交智能、提示词钩子与回复回合追踪。

分类标准：独立功能域（含多文件或强内聚状态）组织为子包；
跨域共用的单文件行为模块（persona/chat_intent/peer_awareness等）
保留为顶层模块，通过本模块统一 re-export。
"""

from .active_learning import ActiveLearning, active_learning
from .chat_intent import (
    SemanticFrameInferrer,
    TurnSemanticFrame,
    semantic_frame_inferrer,
)
from .context import ContextManager, context_manager
from .emotion import EmotionManager, emotion_manager
from .group import ProfileService, profile_service
from .llm import LLMHelper, llm_helper
from .memory import MemoryManager, memory_manager
from .peer_awareness import PeerAwareness, peer_awareness
from .persona import PersonaManager, persona_manager
from .prompt_hooks import (
    HookContext,
    PromptHookRegistry,
    hook_registry,
)
from .reply_turn_trace import (
    ReplyTurnTrace,
    reply_turn_trace,
)
from .runtime import Diagnostics, diagnostics
from .social import (
    SocialContext,
    SocialGate,
    SocialQuota,
    SocialTrigger,
    SocialTriggerRegistry,
    social_gate,
    social_quota,
    social_trigger_registry,
)
from .target_inference import (
    MessageTarget,
    TargetInference,
    target_inference,
)

__all__ = [
    "ActiveLearning",
    "ContextManager",
    "Diagnostics",
    "EmotionManager",
    "HookContext",
    "LLMHelper",
    "MemoryManager",
    "MessageTarget",
    "PeerAwareness",
    "PersonaManager",
    "ProfileService",
    "PromptHookRegistry",
    "ReplyTurnTrace",
    "SemanticFrameInferrer",
    "SocialContext",
    "SocialGate",
    "SocialQuota",
    "SocialTrigger",
    "SocialTriggerRegistry",
    "TargetInference",
    "TurnSemanticFrame",
    "active_learning",
    "context_manager",
    "diagnostics",
    "emotion_manager",
    "hook_registry",
    "llm_helper",
    "memory_manager",
    "peer_awareness",
    "persona_manager",
    "profile_service",
    "reply_turn_trace",
    "semantic_frame_inferrer",
    "social_gate",
    "social_quota",
    "social_trigger_registry",
    "target_inference",
]
