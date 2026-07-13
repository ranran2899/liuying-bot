"""知识库管理器

提供知识条目 CRUD、文档索引与多路检索（FTS5/向量/嵌入/实体）
能力。基于独立 aiosqlite 连接，与 liuying_db 解耦。

检索能力通过 ``KnowledgeRetrieverMixin`` 混入，工具方法集中在
``KnowledgeQueryUtils``，详见 ``retriever`` 模块。

公共 API 通过 ``knowledge_base`` 单例暴露，AI 插件内部调用：
    ```python
    from ..knowledge_db import knowledge_base

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

    提供知识条目 CRUD 与文档索引能力，并通过 ``KnowledgeRetrieverMixin``
    获得 FTS5/向量/嵌入/实体多路检索能力。基于独立 SQLite 数据库。

    通过单例 ``knowledge_base`` 暴露，供 AI 插件内部调用。

    设计两层 API：
    - 高级 API：知识条目 CRUD（add_entry/get_entry/update_entry/...）
    - 低级 API：文档索引（index_document/delete_document/clear_all/...）

    低级 API 供 AI 记忆系统等外部系统使用，doc_id 由调用方管理；
    高级 API 供知识库管理使用，doc_id 由 kb_entries 自增生成。
    """

    __slots__ = ("_conn",)

    def __init__(self) -> None:
        self._conn = kb_connection

    async def init(self) -> None:
        """初始化知识库数据库与表结构（幂等）"""
        await self._conn.init()

    # ---------- 知识条目 CRUD（高级 API） ----------

    @KbConnectionManager.with_write_lock
    async def add_entry(
        self,
        title: str,
        content: str,
        tags: str = "",
        source: str = "",
        metadata: dict | None = None,
        embedding: list[float] | None = None,
        entities: list[dict] | None = None,
        model_version: str = "hash_bow",
    ) -> int:
        """添加知识条目并自动构建检索索引

        参数:
            title: 标题
            content: 内容
            tags: 标签（逗号分隔）
            source: 来源
            metadata: 额外元数据
            embedding: 嵌入向量，None 时跳过向量索引
            entities: 实体列表，每项含 name/type/weight
            model_version: 嵌入模型版本

        返回:
            int: 新条目 doc_id
        """
        meta_str = json.dumps(metadata, ensure_ascii=False) if metadata else None
        db = self._conn.db
        cursor = await db.execute(
            "INSERT INTO kb_entries(title, content, tags, source, metadata) "
            "VALUES(?, ?, ?, ?, ?)",
            (title, content, tags, source, meta_str),
        )
        doc_id = cursor.lastrowid
        await self._index_doc(
            doc_id, content, embedding, entities, meta_str, model_version
        )
        await db.commit()
        return doc_id

    async def get_entry(self, doc_id: int) -> dict | None:
        """获取知识条目

        参数:
            doc_id: 文档 ID

        返回:
            dict | None: 条目字典，不存在返回 None
        """
        cursor = await self._conn.db.execute(
            "SELECT doc_id, title, content, tags, source, metadata, "
            "create_time, update_time FROM kb_entries WHERE doc_id = ?",
            (doc_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return KnowledgeBase._row_to_entry(row)

    async def list_entries(
        self, limit: int = 50, offset: int = 0
    ) -> list[dict]:
        """列出知识条目

        参数:
            limit: 返回上限
            offset: 偏移量

        返回:
            list[dict]: 条目字典列表
        """
        cursor = await self._conn.db.execute(
            "SELECT doc_id, title, content, tags, source, metadata, "
            "create_time, update_time FROM kb_entries "
            "ORDER BY doc_id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cursor.fetchall()
        return [KnowledgeBase._row_to_entry(row) for row in rows]

    @KbConnectionManager.with_write_lock
    async def update_entry(
        self,
        doc_id: int,
        title: str | None = None,
        content: str | None = None,
        tags: str | None = None,
        source: str | None = None,
        metadata: dict | None = None,
        embedding: list[float] | None = None,
        entities: list[dict] | None = None,
        model_version: str = "hash_bow",
    ) -> bool:
        """更新知识条目并重建检索索引

        参数:
            doc_id: 文档 ID
            title: 标题，None 时不更新
            content: 内容，None 时不更新（也不重建索引）
            tags: 标签，None 时不更新
            source: 来源，None 时不更新
            metadata: 元数据，None 时不更新
            embedding: 嵌入向量，None 时跳过
            entities: 实体列表，None 时跳过
            model_version: 嵌入模型版本

        返回:
            bool: 是否更新成功（条目不存在返回 False）
        """
        cursor = await self._conn.db.execute(
            "SELECT 1 FROM kb_entries WHERE doc_id = ?", (doc_id,)
        )
        if await cursor.fetchone() is None:
            return False

        fields: list[str] = []
        params: list = []
        if title is not None:
            fields.append("title = ?")
            params.append(title)
        if content is not None:
            fields.append("content = ?")
            params.append(content)
        if tags is not None:
            fields.append("tags = ?")
            params.append(tags)
        if source is not None:
            fields.append("source = ?")
            params.append(source)
        if metadata is not None:
            fields.append("metadata = ?")
            params.append(json.dumps(metadata, ensure_ascii=False))
        fields.append("update_time = datetime('now')")
        params.append(doc_id)
        await self._conn.db.execute(
            f"UPDATE kb_entries SET {', '.join(fields)} WHERE doc_id = ?",
            params,
        )
        if content is not None:
            meta_cursor = await self._conn.db.execute(
                "SELECT metadata FROM kb_entries WHERE doc_id = ?", (doc_id,)
            )
            meta_row = await meta_cursor.fetchone()
            meta_str = meta_row["metadata"] if meta_row else None
            await self._index_doc(
                doc_id, content, embedding, entities, meta_str, model_version
            )
        await self._conn.db.commit()
        return True

    @KbConnectionManager.with_write_lock
    async def delete_entry(self, doc_id: int) -> bool:
        """删除知识条目及其全部检索索引

        参数:
            doc_id: 文档 ID

        返回:
            bool: 是否删除成功（条目不存在返回 False）
        """
        cursor = await self._conn.db.execute(
            "DELETE FROM kb_entries WHERE doc_id = ?", (doc_id,)
        )
        deleted = cursor.rowcount > 0
        await self._delete_all_indexes(doc_id)
        await self._conn.db.commit()
        return deleted

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
        """清空所有知识库表数据

        谨慎使用：仅用于重置场景。
        """
        db = self._conn.db
        for table in (
            "kb_entries",
            "kb_fts_idx",
            "kb_fts_text",
            "kb_embeddings",
            "kb_vector_chunks",
            "kb_entities",
            "kb_relations",
        ):
            await db.execute(f"DELETE FROM {table}")
        await db.commit()
        logger.warning("已清空所有知识库表数据", command=_LOG_CMD)

    # ---------- 实体关系 ----------

    @KbConnectionManager.with_write_lock
    async def add_relation(
        self,
        subject: str,
        relation: str,
        obj: str,
        weight: float = 1.0,
        doc_id: int | None = None,
    ) -> None:
        """添加实体关系（知识图谱三元组）

        参数:
            subject: 主体实体名
            relation: 关系名
            obj: 客体实体名
            weight: 关系权重
            doc_id: 关联文档 ID，可选
        """
        await self._conn.db.execute(
            "INSERT INTO kb_relations"
            "(subject, relation, object, weight, doc_id) "
            "VALUES(?, ?, ?, ?, ?)",
            (subject, relation, obj, weight, doc_id),
        )
        await self._conn.db.commit()

    async def get_relations(
        self, subject: str, limit: int = 50
    ) -> list[dict]:
        """按主体查询关系

        参数:
            subject: 主体实体名
            limit: 返回条数上限

        返回:
            list[dict]: 关系列表
        """
        cursor = await self._conn.db.execute(
            "SELECT subject, relation, object, weight, doc_id "
            "FROM kb_relations WHERE subject = ? "
            "ORDER BY weight DESC LIMIT ?",
            (subject, limit),
        )
        rows = await cursor.fetchall()
        return [
            {
                "subject": row["subject"],
                "relation": row["relation"],
                "object": row["object"],
                "weight": row["weight"],
                "doc_id": row["doc_id"],
            }
            for row in rows
        ]

    # ---------- 内部辅助方法 ----------

    @staticmethod
    def _row_to_entry(row) -> dict:
        """将数据库行转换为条目字典

        供 get_entry/list_entries 复用，统一字段映射与 metadata 反序列化。

        参数:
            row: 数据库行对象

        返回:
            dict: 条目字典
        """
        return {
            "doc_id": row["doc_id"],
            "title": row["title"],
            "content": row["content"],
            "tags": row["tags"],
            "source": row["source"],
            "metadata": (
                json.loads(row["metadata"]) if row["metadata"] else None
            ),
            "create_time": row["create_time"],
            "update_time": row["update_time"],
        }

    async def _index_doc(
        self,
        doc_id: int,
        text: str,
        embedding: list[float] | None,
        entities: list[dict] | None,
        meta_str: str | None,
        model_version: str,
    ) -> None:
        """内部：写入文档索引（FTS + 向量 + 实体）"""
        db = self._conn.db
        await self._write_fts(db, doc_id, text, meta_str)
        if embedding is not None:
            await db.execute(
                "INSERT OR REPLACE INTO kb_embeddings"
                "(doc_id, embedding, model_version, dim) "
                "VALUES(?, ?, ?, ?)",
                (doc_id, json.dumps(embedding), model_version, len(embedding)),
            )
        if entities:
            await self._write_entities(db, doc_id, entities)

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
            "kb_relations",
        ):
            await db.execute(
                f"DELETE FROM {table} WHERE doc_id = ?", (doc_id,)
            )


knowledge_base = KnowledgeBase()
"""知识库管理器单例，AI 插件内部统一通过此单例访问知识库能力"""
