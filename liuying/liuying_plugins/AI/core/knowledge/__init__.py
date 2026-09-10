"""知识库

复用 help 插件 HelpManage 的插件查询接口获取插件信息，
支持多维度检索、智能召回、知识块构建与查询日志。
"""

from .store import (
    KnowledgeStore,
    knowledge_store,
)
from .types import KnowledgeStats, RecallResult

__all__ = [
    "KnowledgeStats",
    "KnowledgeStore",
    "RecallResult",
    "knowledge_store",
]
