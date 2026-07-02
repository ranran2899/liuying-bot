"""搜索模块（FTS5 全文检索 + 向量存储 + 实体关系管理）

提供统一的搜索能力，支持 SQLite 文件存储。基于原生 SQL 实现，
避开 SQLAlchemy ORM 对 FTS5 虚拟表的不支持问题。

模块结构:
- schema.py: 表结构 DDL 与初始化
- fts.py: FTSManager 全文检索
- vector.py: VectorManager 向量存储与检索
- entity.py: EntityManager 实体与关系管理
- manager.py: SearchManager 统一门面

使用示例:
    ```python
    from liuying.services.liuying_db import search_manager

    # 初始化表结构
    await search_manager.init()

    # FTS 索引与检索
    await search_manager.fts.upsert(1, "流萤今天去星海了")
    results = await search_manager.fts.search("星海", limit=5)

    # 向量存储与检索
    await search_manager.vector.store_embedding(1, [0.1, 0.2, ...])
    results = await search_manager.vector.vector_search(query_vec, top_k=5)

    # 实体管理
    await search_manager.entity.upsert_entities(1, [
        {"name": "流萤", "type": "character", "weight": 1.5}
    ])

    # 原子删除文档所有索引数据
    await search_manager.delete_document(1)
    ```
"""

from .entity import EntityManager
from .fts import FTSManager
from .manager import SearchManager, search_manager
from .schema import SEARCH_DDL, init_search_tables
from .vector import VectorManager, cosine_similarity

__all__ = [
    "SEARCH_DDL",
    "EntityManager",
    "FTSManager",
    "SearchManager",
    "VectorManager",
    "cosine_similarity",
    "init_search_tables",
    "search_manager",
]
