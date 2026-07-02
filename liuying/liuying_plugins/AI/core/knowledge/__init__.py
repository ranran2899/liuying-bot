"""知识库

提供基于流萤本体插件系统的插件视图与知识库查询接口。
通过 PluginInfo + NoneBot 实时元信息构建插件视图，
支持多维度检索、智能召回、知识块构建与查询日志。

附加模块：
- 知识书（Lorebook）：按关键词触发注入扩展知识到 prompt
- 网络梗词典（MemeDictionary）：预置常用网络梗解释
- 人设专属知识库（PersonaKnowledge）：按人格名隔离的临时知识
"""

from .lorebook import Lorebook, lorebook
from .meme_dict import MemeDictionary, meme_dictionary
from .persona_knowledge import PersonaKnowledge, persona_knowledge
from .store import (
    KnowledgeStore,
    PluginView,
    knowledge_store,
)
from .types import KnowledgeStats, RecallResult

__all__ = [
    "KnowledgeStats",
    "KnowledgeStore",
    "Lorebook",
    "MemeDictionary",
    "PersonaKnowledge",
    "PluginView",
    "RecallResult",
    "knowledge_store",
    "lorebook",
    "meme_dictionary",
    "persona_knowledge",
]
