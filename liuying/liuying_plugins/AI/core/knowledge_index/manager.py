"""知识库管理器

提供文档索引与多路检索（FTS5/向量/嵌入/实体）能力。
基于独立 aiosqlite 连接，与 liuying_db 解耦。

检索能力通过 ``KnowledgeRetrieverMixin`` 混入，工具方法集中在
``KnowledgeQueryUtils``，详见 ``retriever`` 模块。

公共 API 通过 ``knowledge_base`` 单例暴露，AI 插件内部调用：
    ```python
    from ..knowledge_index import knowledge_base

    await knowledge_base.init()
    await knowledge_base.index_document(1, "文本", embedding=[...])
    results = await knowledge_base.search_fts("查询", limit=5)
    ```
"""

import json

from liuying.utils.log import logger

from .connection import KbConnectionManager, kb_connection
from .retriever import KnowledgeRetrieverMixin

_LOG_CMD = "knowledge_base"
"""日志 command 标识"""


class KnowledgeBase(KnowledgeRetrieverMixin):
    """知识库管理器

    提供文档索引能力，并通过 ``KnowledgeRetrieverMixin``
    获得 FTS5/向量/嵌入/实体多路检索能力。基于独立 SQLite 数据库。

    通过单例 ``knowledge_base`` 暴露，供 AI 插件内部调用。

    提供 index_document/delete_document/clear_all 等文档索引 API，
    供 AI 记忆系统等外部系统使用，doc_id 由调用方管理。
    """

    __slots__ = ("_conn",)

    def __init__(self) -> None:
        self._conn = kb_connection

    async def init(self) -> None:
        """初始化知识库数据库与表结构（幂等）"""
        await self._conn.init()

    # ---------- 文档索引服务（低级 API） ----------

    @KbConnectionManager.with_write_lock
    async def index_document(
        self,
        doc_id: int,
        text: str,
        embedding: list[float] | None = None,
        chunks: list[dict] | None = None,
        entities: list[dict] | None = None,
        metadata: dict | None = None,
        model_version: str = "hash_bow",
    ) -> None:
        """原子写入一个文档的全部索引数据

        在单个事务内同时写入 FTS、向量、实体数据，保证一致性。
        doc_id 由调用方管理（如 AI 记忆系统的 memory.id）。

        参数:
            doc_id: 文档 ID
            text: 索引文本
            embedding: 主嵌入向量，None 时跳过
            chunks: 分块向量列表，None 时跳过
            entities: 实体列表，None 时跳过
            metadata: 可选元数据
            model_version: 嵌入模型版本
        """
        meta_str = json.dumps(metadata, ensure_ascii=False) if metadata else None
        db = self._conn.db
        await self._write_fts(db, doc_id, text, meta_str)
        if embedding is not None:
            await db.execute(
                "INSERT OR REPLACE INTO kb_embeddings"
                "(doc_id, embedding, model_version, dim) "
                "VALUES(?, ?, ?, ?)",
                (doc_id, json.dumps(embedding), model_version, len(embedding)),
            )
        if chunks:
            await db.execute(
                "DELETE FROM kb_vector_chunks WHERE doc_id = ?", (doc_id,)
            )
            for idx, chunk in enumerate(chunks):
                vec = chunk.get("vector", [])
                await db.execute(
                    "INSERT INTO kb_vector_chunks"
                    "(doc_id, chunk_index, vector, salience, confidence, "
                    "model_version, embedding_dim) VALUES(?, ?, ?, ?, ?, ?, ?)",
                    (
                        doc_id,
                        idx,
                        json.dumps(vec),
                        chunk.get("salience", 0.5),
                        chunk.get("confidence", 0.5),
                        chunk.get("model_version", model_version),
                        len(vec),
                    ),
                )
        if entities:
            await self._write_entities(db, doc_id, entities)
        await db.commit()

    @KbConnectionManager.with_write_lock
    async def delete_document(self, doc_id: int) -> None:
        """原子删除一个文档的全部索引数据

        参数:
            doc_id: 文档 ID
        """
        await self._delete_all_indexes(doc_id)
        await self._conn.db.commit()

    @KbConnectionManager.with_write_lock
    async def clear_all(self) -> None:
        """清空知识库索引表数据

        清空全部检索索引表（FTS/向量/嵌入/实体），
        供记忆系统等索引类调用方完全重置使用。
        """
        db = self._conn.db
        tables = [
            "kb_fts_idx",
            "kb_fts_text",
            "kb_embeddings",
            "kb_vector_chunks",
            "kb_entities",
        ]
        for table in tables:
            await db.execute(f"DELETE FROM {table}")
        await db.commit()
        logger.warning(
            "已清空知识库索引表数据",
            command=_LOG_CMD,
        )

    # ---------- 内部辅助方法 ----------

    async def _write_fts(
        self,
        db,
        doc_id: int,
        text: str,
        meta_str: str | None,
    ) -> None:
        """内部：写入 FTS 索引与原文"""
        await db.execute(
            "DELETE FROM kb_fts_idx WHERE doc_id = ?", (doc_id,)
        )
        await db.execute(
            "INSERT INTO kb_fts_idx(doc_id, content) VALUES(?, ?)",
            (doc_id, text),
        )
        await db.execute(
            "INSERT OR REPLACE INTO kb_fts_text"
            "(doc_id, text, metadata) VALUES(?, ?, ?)",
            (doc_id, text, meta_str),
        )

    async def _write_entities(
        self,
        db,
        doc_id: int,
        entities: list[dict],
    ) -> None:
        """内部：写入实体标注"""
        await db.execute(
            "DELETE FROM kb_entities WHERE doc_id = ?", (doc_id,)
        )
        for ent in entities:
            await db.execute(
                "INSERT INTO kb_entities"
                "(doc_id, entity_name, entity_type, weight) "
                "VALUES(?, ?, ?, ?)",
                (
                    doc_id,
                    ent.get("name", ""),
                    ent.get("type", "general"),
                    ent.get("weight", 1.0),
                ),
            )

    async def _delete_all_indexes(self, doc_id: int) -> None:
        """内部：删除文档的全部索引数据"""
        db = self._conn.db
        for table in (
            "kb_fts_idx",
            "kb_fts_text",
            "kb_embeddings",
            "kb_vector_chunks",
            "kb_entities",
        ):
            await db.execute(
                f"DELETE FROM {table} WHERE doc_id = ?", (doc_id,)
            )


knowledge_base = KnowledgeBase()
"""知识库管理器单例，AI 插件内部统一通过此单例访问知识库能力"""
