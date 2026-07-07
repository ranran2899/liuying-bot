"""知识库管理器

提供知识条目 CRUD、文档索引、多路检索（FTS5/向量/嵌入/实体）
与统一融合检索能力。基于独立 aiosqlite 连接，与 liuying_db 解耦。

公共 API 通过 ``knowledge_base`` 单例暴露，AI 插件内部调用：
    ```python
    from ..knowledge_db import knowledge_base

    await knowledge_base.init()
    await knowledge_base.index_document(1, "文本", embedding=[...])
    results = await knowledge_base.search_fts("查询", limit=5)
    ```
"""

import json
import math
import re

from liuying.utils.log import logger

from .connection import kb_connection, with_write_lock

_LOG_CMD = "knowledge_base"
"""日志 command 标识"""

_RRF_K = 60
"""RRF 融合参数"""


def cosine_similarity(
    vec_a: list[float], vec_b: list[float]
) -> float:
    """计算两个向量的余弦相似度

    参数:
        vec_a: 向量 A
        vec_b: 向量 B

    返回:
        float: 余弦相似度（-1 到 1，越大越相似）
    """
    min_len = min(len(vec_a), len(vec_b))
    if min_len == 0:
        return 0.0
    dot = sum(vec_a[i] * vec_b[i] for i in range(min_len))
    norm_a = math.sqrt(sum(x * x for x in vec_a[:min_len]))
    norm_b = math.sqrt(sum(x * x for x in vec_b[:min_len]))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _tokenize_query(query: str) -> list[str]:
    """对查询文本做简单分词

    将标点符号替换为空格后按空白拆分，保留中文、英文与数字词元。

    参数:
        query: 原始查询文本

    返回:
        list[str]: 分词后的词元列表
    """
    cleaned = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", query)
    return [token for token in cleaned.split() if token]


def _build_match_query(query: str, mode: str) -> str:
    """根据模式构建 FTS5 MATCH 查询字符串

    参数:
        query: 原始查询文本
        mode: 匹配模式，"phrase" 为短语匹配，"or" 为分词后 OR 匹配

    返回:
        str: 可用于 FTS5 MATCH 的查询字符串
    """
    escaped = query.replace('"', '""')
    if mode == "phrase" or not escaped.strip():
        return f'"{escaped}"'
    tokens = _tokenize_query(query)
    if not tokens:
        return f'"{escaped}"'
    escaped_tokens = [t.replace('"', '""') for t in tokens]
    return " OR ".join(f'"{t}"' for t in escaped_tokens)


class KnowledgeBase:
    """知识库管理器

    提供知识条目 CRUD 与多路检索能力，基于独立 SQLite 数据库。
    通过单例 ``knowledge_base`` 暴露，供 AI 插件内部调用。

    设计两层 API：
    - 高级 API：知识条目 CRUD（add_entry/get_entry/update_entry/...）
    - 低级 API：文档索引与检索（index_document/search_fts/...）

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

    @with_write_lock
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
        return {
            "doc_id": row["doc_id"],
            "title": row["title"],
            "content": row["content"],
            "tags": row["tags"],
            "source": row["source"],
            "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
            "create_time": row["create_time"],
            "update_time": row["update_time"],
        }

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
        return [
            {
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
            for row in rows
        ]

    @with_write_lock
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

    @with_write_lock
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

    @with_write_lock
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

    @with_write_lock
    async def delete_document(self, doc_id: int) -> None:
        """原子删除一个文档的全部索引数据

        参数:
            doc_id: 文档 ID
        """
        await self._delete_all_indexes(doc_id)
        await self._conn.db.commit()

    @with_write_lock
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
        logger.warning("已清空所有知识库表数据", _LOG_CMD)

    # ---------- 检索能力 ----------

    async def search_fts(
        self,
        query: str,
        limit: int = 10,
        mode: str = "or",
    ) -> list[tuple[int, float]]:
        """FTS5 全文检索

        参数:
            query: 查询文本
            limit: 返回条数上限
            mode: 匹配模式，"phrase" 为短语匹配，"or" 为分词 OR 匹配

        返回:
            list[tuple[int, float]]: (doc_id, score) 列表，按分数降序
        """
        if not query.strip():
            return []
        match_query = _build_match_query(query, mode)
        cursor = await self._conn.db.execute(
            "SELECT doc_id, rank FROM kb_fts_idx "
            "WHERE content MATCH ? ORDER BY rank LIMIT ?",
            (match_query, limit),
        )
        rows = await cursor.fetchall()
        return [
            (row["doc_id"], max(0.0, 1.0 / (1.0 + abs(row["rank"]))))
            for row in rows
        ]

    async def search_vector(
        self,
        query_vec: list[float],
        top_k: int = 10,
        model_version: str | None = "hash_bow",
    ) -> list[tuple[int, float]]:
        """向量分块余弦相似度检索

        参数:
            query_vec: 查询向量
            top_k: 返回条数上限
            model_version: 模型版本，None 时不按版本过滤

        返回:
            list[tuple[int, float]]: (doc_id, similarity) 列表
        """
        return await self._vector_search(
            "kb_vector_chunks", "vector", "embedding_dim",
            query_vec, top_k, model_version,
        )

    async def search_embedding(
        self,
        query_vec: list[float],
        top_k: int = 10,
        model_version: str | None = "hash_bow",
    ) -> list[tuple[int, float]]:
        """主向量嵌入相似度检索

        与 search_vector 区别：在主嵌入表而非分块表中检索。

        参数:
            query_vec: 查询向量
            top_k: 返回条数上限
            model_version: 模型版本，None 时不按版本过滤

        返回:
            list[tuple[int, float]]: (doc_id, similarity) 列表
        """
        return await self._vector_search(
            "kb_embeddings", "embedding", "dim",
            query_vec, top_k, model_version,
        )

    async def search_entity(
        self,
        entity_names: list[str],
        top_k: int = 10,
    ) -> list[tuple[int, float]]:
        """实体检索

        按实体名匹配文档，按权重求和后归一化打分。

        参数:
            entity_names: 实体名列表
            top_k: 返回条数上限

        返回:
            list[tuple[int, float]]: (doc_id, score) 列表，按分数降序
        """
        if not entity_names:
            return []
        placeholders = ",".join("?" * len(entity_names))
        cursor = await self._conn.db.execute(
            f"SELECT doc_id, SUM(weight) as total "
            f"FROM kb_entities WHERE entity_name IN ({placeholders}) "
            f"GROUP BY doc_id ORDER BY total DESC LIMIT ?",
            (*entity_names, top_k),
        )
        rows = await cursor.fetchall()
        if not rows:
            return []
        max_score = rows[0]["total"] or 1.0
        return [
            (row["doc_id"], (row["total"] or 0.0) / max_score) for row in rows
        ]

    async def unified_search(
        self,
        query: str = "",
        query_vec: list[float] | None = None,
        entity_names: list[str] | None = None,
        top_k: int = 10,
        model_version: str = "hash_bow",
    ) -> list[tuple[int, float]]:
        """统一融合检索（RRF）

        并行执行 FTS、向量、嵌入、实体四路召回，用 RRF 融合结果。

        参数:
            query: 查询文本，空串时跳过 FTS
            query_vec: 查询向量，None 时跳过向量检索
            entity_names: 实体名列表，None 时跳过实体检索
            top_k: 返回条数上限
            model_version: 嵌入模型版本

        返回:
            list[tuple[int, float]]: (doc_id, score) 列表，按分数降序
        """
        candidates: dict[int, float] = {}
        if query.strip():
            for rank, (doc_id, _) in enumerate(
                await self.search_fts(query, top_k * 3)
            ):
                candidates[doc_id] = candidates.get(doc_id, 0.0) + (
                    1.0 / (_RRF_K + rank + 1)
                )
        if query_vec is not None:
            for rank, (doc_id, _) in enumerate(
                await self.search_vector(query_vec, top_k * 3, model_version)
            ):
                candidates[doc_id] = candidates.get(doc_id, 0.0) + (
                    1.0 / (_RRF_K + rank + 1)
                )
            for rank, (doc_id, _) in enumerate(
                await self.search_embedding(query_vec, top_k * 3, model_version)
            ):
                candidates[doc_id] = candidates.get(doc_id, 0.0) + (
                    1.0 / (_RRF_K + rank + 1)
                )
        if entity_names:
            for rank, (doc_id, _) in enumerate(
                await self.search_entity(entity_names, top_k * 3)
            ):
                candidates[doc_id] = candidates.get(doc_id, 0.0) + (
                    1.0 / (_RRF_K + rank + 1)
                )
        return sorted(
            candidates.items(), key=lambda x: x[1], reverse=True
        )[:top_k]

    # ---------- 获取器 ----------

    async def get_text(self, doc_id: int) -> str | None:
        """获取指定文档的原始索引文本

        参数:
            doc_id: 文档 ID

        返回:
            str | None: 原始文本，不存在返回 None
        """
        cursor = await self._conn.db.execute(
            "SELECT text FROM kb_fts_text WHERE doc_id = ?", (doc_id,)
        )
        row = await cursor.fetchone()
        return row["text"] if row else None

    async def get_embedding(self, doc_id: int) -> list[float] | None:
        """获取文档的主嵌入向量

        参数:
            doc_id: 文档 ID

        返回:
            list[float] | None: 嵌入向量，不存在返回 None
        """
        cursor = await self._conn.db.execute(
            "SELECT embedding FROM kb_embeddings WHERE doc_id = ?", (doc_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        try:
            return json.loads(row["embedding"])
        except (json.JSONDecodeError, TypeError):
            return None

    # ---------- 实体关系 ----------

    @with_write_lock
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

    async def _vector_search(
        self,
        table: str,
        vec_col: str,
        dim_col: str,
        query_vec: list[float],
        top_k: int,
        model_version: str | None,
    ) -> list[tuple[int, float]]:
        """内部：向量相似度检索通用实现"""
        params: list = [len(query_vec)]
        sql = f"SELECT doc_id, {vec_col} FROM {table} WHERE {dim_col} = ?"
        if model_version is not None:
            sql += " AND model_version = ?"
            params.append(model_version)
        cursor = await self._conn.db.execute(sql, params)
        rows = await cursor.fetchall()
        if not rows:
            return []
        scored: list[tuple[int, float]] = []
        for row in rows:
            try:
                vec = json.loads(row[vec_col])
            except (json.JSONDecodeError, TypeError):
                continue
            sim = cosine_similarity(query_vec, vec)
            scored.append((row["doc_id"], sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]


knowledge_base = KnowledgeBase()
"""知识库管理器单例，AI 插件内部统一通过此单例访问知识库能力"""
