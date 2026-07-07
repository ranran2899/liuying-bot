"""知识库包

基于 SQLite 的独立知识库系统，提供 FTS5 全文检索、向量检索、
实体检索与知识图谱能力。完全独立于 liuying_db，使用专属
SQLite 数据库文件（data/db/knowledge_base.db）。

公共 API 通过 ``knowledge_base`` 单例暴露，AI 插件内部调用：
    ```python
    from ..knowledge_db import knowledge_base

    # 知识条目 CRUD
    doc_id = await knowledge_base.add_entry("标题", "内容")
    entry = await knowledge_base.get_entry(doc_id)

    # 文档索引（供 AI 记忆系统等使用）
    await knowledge_base.index_document(1, "文本", embedding=[...])

    # 多路检索
    results = await knowledge_base.search_fts("查询")
    results = await knowledge_base.unified_search("查询", query_vec=[...])
    ```
"""

from .connection import KbConnectionManager, kb_connection
from .manager import KnowledgeBase, cosine_similarity, knowledge_base

__all__ = [
    "KbConnectionManager",
    "KnowledgeBase",
    "cosine_similarity",
    "kb_connection",
    "knowledge_base",
]
"""知识库包公开 API"""
