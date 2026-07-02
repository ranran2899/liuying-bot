"""记忆系统

提供多层级记忆管理（工作/情景/语义/背景）、记忆整理、记忆进化、
向量嵌入、实体索引、记忆摘要、主动学习与后台智能处理。
"""

from .active_learning import ActiveLearner, active_learner
from .background import BackgroundIntelligence, background_intelligence
from .curator import CurationReport, MemoryCurator, memory_curator
from .entity_index import EntityIndexer, entity_indexer
from .evolves import MemoryEvolver, memory_evolver
from .extractors import EntityMention
from .manager import MemoryManager, memory_manager
from .summarizer import MemorySummarizer, memory_summarizer

__all__ = [
    "ActiveLearner",
    "BackgroundIntelligence",
    "CurationReport",
    "EntityIndexer",
    "EntityMention",
    "MemoryCurator",
    "MemoryEvolver",
    "MemoryManager",
    "MemorySummarizer",
    "active_learner",
    "background_intelligence",
    "entity_indexer",
    "memory_curator",
    "memory_evolver",
    "memory_manager",
    "memory_summarizer",
]
