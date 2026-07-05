"""核心服务层

提供LLM调用封装、人格管理、记忆系统、情绪状态、上下文管理、
画像服务与运行时开关。
所有能力按功能子包组织，通过本模块统一 re-export。
"""

from .context import ContextManager, context_manager
from .emotion import EmotionManager, emotion_manager
from .group import ProfileService, profile_service
from .llm import LLMHelper, llm_helper
from .memory import MemoryManager, memory_manager
from .persona import PersonaManager, persona_manager
from .runtime import Diagnostics, diagnostics

__all__ = [
    "ContextManager",
    "Diagnostics",
    "EmotionManager",
    "LLMHelper",
    "MemoryManager",
    "PersonaManager",
    "ProfileService",
    "context_manager",
    "diagnostics",
    "emotion_manager",
    "llm_helper",
    "memory_manager",
    "persona_manager",
    "profile_service",
]
