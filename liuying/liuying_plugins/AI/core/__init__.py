"""核心服务层

提供LLM调用封装、人格管理、记忆系统、情绪状态、上下文管理、
画像服务、人设知识库、知识书、后台智能、主动诊断、网络梗词典。
所有能力按功能子包组织，通过本模块统一 re-export。
"""

from .context import ContextManager, context_manager
from .emotion import EmotionManager, emotion_manager
from .group import ProfileService, profile_service
from .knowledge import (
    Lorebook,
    MemeDictionary,
    PersonaKnowledge,
    lorebook,
    meme_dictionary,
    persona_knowledge,
)
from .llm import LLMHelper, llm_helper
from .memory import (
    BackgroundIntelligence,
    MemoryManager,
    background_intelligence,
    memory_manager,
)
from .persona import PersonaManager, persona_manager
from .runtime import Diagnostics, diagnostics

__all__ = [
    "BackgroundIntelligence",
    "ContextManager",
    "Diagnostics",
    "EmotionManager",
    "LLMHelper",
    "Lorebook",
    "MemeDictionary",
    "MemoryManager",
    "PersonaKnowledge",
    "PersonaManager",
    "ProfileService",
    "background_intelligence",
    "context_manager",
    "diagnostics",
    "emotion_manager",
    "llm_helper",
    "lorebook",
    "meme_dictionary",
    "memory_manager",
    "persona_knowledge",
    "persona_manager",
    "profile_service",
]
