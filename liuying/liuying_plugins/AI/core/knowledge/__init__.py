"""知识库

提供基于流萤本体插件系统的插件视图与知识库查询接口。
通过 PluginInfo + NoneBot 实时元信息构建插件视图，
支持多维度检索、智能召回、知识块构建与查询日志。
"""

from .store import (
    KnowledgeStore,
    PluginView,
    knowledge_store,
)
from .types import KnowledgeStats, RecallResult

__all__ = [
    "KnowledgeStats",
    "KnowledgeStore",
    "PluginView",
    "RecallResult",
    "knowledge_store",
]
