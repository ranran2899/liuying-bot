"""知识库检索能力

提供 FTS5 全文检索、向量分块检索、主嵌入检索与实体检索能力。
通过 ``KnowledgeRetrieverMixin`` 混入 ``KnowledgeBase``，
复用其 ``_conn`` 连接管理。

公共 API 仍通过 ``knowledge_base`` 单例暴露，调用方无感知：
    ```python
    from ..knowledge_db import knowledge_base

    results = await knowledge_base.search_fts("查询", limit=5)
    ```
"""

import json
import math
import re

_VECTOR_SCAN_CAP = 2000
"""向量检索单次扫描行数上限，避免全表拉取向量逐行计算"""


class KnowledgeQueryUtils:
    """知识库查询工具类

    提供向量相似度、查询分词与 FTS5 MATCH 构建等纯计算工具方法。
    所有方法为静态方法，无状态依赖。
    """

    @staticmethod
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

    @staticmethod
    def tokenize_query(query: str) -> list[str]:
        """对查询文本做简单分词

        将标点符号替换为空格后按空白拆分，保留中文、英文与数字词元。

        参数:
            query: 原始查询文本

        返回:
            list[str]: 分词后的词元列表
        """
        cleaned = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", query)
        return [token for token in cleaned.split() if token]

    @staticmethod
    def build_match_query(query: str, mode: str) -> str:
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
        tokens = KnowledgeQueryUtils.tokenize_query(query)
        if not tokens:
            return f'"{escaped}"'
        escaped_tokens = [t.replace('"', '""') for t in tokens]
        return " OR ".join(f'"{t}"' for t in escaped_tokens)


class KnowledgeRetrieverMixin:
    """知识库检索能力混入类

    提供 FTS5/向量/嵌入/实体多路检索与 RRF 融合能力。
    假设宿主类已提供 ``_conn`` 属性（``KbConnectionManager`` 实例）。

    通过混入 ``KnowledgeBase`` 复用其连接，调用方无需感知分离。
    """

    __slots__ = ()

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
        match_query = KnowledgeQueryUtils.build_match_query(query, mode)
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
        user_id: str | None = None,
        persona_name: str | None = None,
    ) -> list[tuple[int, float]]:
        """向量分块余弦相似度检索

        归属过滤：向量表无 user/persona 列（归属存于
        kb_fts_text.metadata JSON 文本列，无法 SQL 过滤），
        提供 user_id/persona_name 时在 Python 侧按 metadata
        批量过滤；未提供时不过滤，行为与旧版一致。

        参数:
            query_vec: 查询向量
            top_k: 返回条数上限
            model_version: 模型版本，None 时不按版本过滤
            user_id: 用户ID，提供时仅保留该用户的文档
            persona_name: bot人格名，提供时仅保留该人格的文档

        返回:
            list[tuple[int, float]]: (doc_id, similarity) 列表
        """
        return await self._vector_search(
            "kb_vector_chunks",
            "vector",
            "embedding_dim",
            "id",
            query_vec,
            top_k,
            model_version,
            user_id=user_id,
            persona_name=persona_name,
        )

    async def search_embedding(
        self,
        query_vec: list[float],
        top_k: int = 10,
        model_version: str | None = "hash_bow",
        user_id: str | None = None,
        persona_name: str | None = None,
    ) -> list[tuple[int, float]]:
        """主向量嵌入相似度检索

        与 search_vector 区别：在主嵌入表而非分块表中检索。
        归属过滤机制与 search_vector 一致（Python 侧按
        kb_fts_text.metadata 过滤）。

        参数:
            query_vec: 查询向量
            top_k: 返回条数上限
            model_version: 模型版本，None 时不按版本过滤
            user_id: 用户ID，提供时仅保留该用户的文档
            persona_name: bot人格名，提供时仅保留该人格的文档

        返回:
            list[tuple[int, float]]: (doc_id, similarity) 列表
        """
        return await self._vector_search(
            "kb_embeddings",
            "embedding",
            "dim",
            "doc_id",
            query_vec,
            top_k,
            model_version,
            user_id=user_id,
            persona_name=persona_name,
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
            (row["doc_id"], (row["total"] or 0.0) / max_score)
            for row in rows
        ]

    # ---------- 内部辅助方法 ----------

    async def _vector_search(
        self,
        table: str,
        vec_col: str,
        dim_col: str,
        order_col: str,
        query_vec: list[float],
        top_k: int,
        model_version: str | None,
        user_id: str | None = None,
        persona_name: str | None = None,
    ) -> list[tuple[int, float]]:
        """内部：向量相似度检索通用实现

        向量表无独立时间列，order_col 为自增主键/文档 ID，
        作为写入时间倒序的近似代理；配合 LIMIT 扫描上限，
        避免无界全表拉取向量后逐行 json.loads 计算余弦。

        参数:
            table: 目标表名
            vec_col: 向量列名
            dim_col: 维度列名
            order_col: 排序列名（近似时间倒序代理）
            query_vec: 查询向量
            top_k: 返回条数上限
            model_version: 模型版本，None 时不按版本过滤
            user_id: 用户ID，提供时按 metadata 过滤归属
            persona_name: bot人格名，提供时按 metadata 过滤归属

        返回:
            list[tuple[int, float]]: (doc_id, similarity) 列表
        """
        params: list = [len(query_vec)]
        sql = f"SELECT doc_id, {vec_col} FROM {table} WHERE {dim_col} = ?"
        if model_version is not None:
            sql += " AND model_version = ?"
            params.append(model_version)
        sql += f" ORDER BY {order_col} DESC LIMIT ?"
        params.append(_VECTOR_SCAN_CAP)
        cursor = await self._conn.db.execute(sql, params)
        rows = await cursor.fetchall()
        if not rows:
            return []
        rows = await self._filter_by_owner(rows, user_id, persona_name)
        if not rows:
            return []
        scored: list[tuple[int, float]] = []
        for row in rows:
            try:
                vec = json.loads(row[vec_col])
            except (json.JSONDecodeError, TypeError):
                continue
            sim = KnowledgeQueryUtils.cosine_similarity(query_vec, vec)
            scored.append((row["doc_id"], sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    async def _filter_by_owner(
        self,
        rows: list,
        user_id: str | None,
        persona_name: str | None,
    ) -> list:
        """内部：按归属过滤向量检索结果行

        向量表无 user/persona 列，归属存于 kb_fts_text.metadata
        （JSON 文本列）无法 SQL WHERE 过滤，故一次性批量查询
        metadata 后在 Python 侧过滤。metadata 缺失或损坏的行
        视为不匹配（index_document 始终写入 metadata，正常
        数据不受影响）。

        参数:
            rows: 向量检索结果行
            user_id: 用户ID，None 时不按用户过滤
            persona_name: bot人格名，None 时不按人格过滤

        返回:
            list: 过滤后的行列表
        """
        if user_id is None and persona_name is None:
            return rows
        doc_ids = list({row["doc_id"] for row in rows})
        placeholders = ",".join("?" * len(doc_ids))
        cursor = await self._conn.db.execute(
            f"SELECT doc_id, metadata FROM kb_fts_text "
            f"WHERE doc_id IN ({placeholders})",
            doc_ids,
        )
        meta_rows = await cursor.fetchall()
        matched: set[int] = set()
        for meta in meta_rows:
            try:
                data = json.loads(meta["metadata"] or "{}")
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(data, dict):
                continue
            if user_id is not None and data.get("user_id") != user_id:
                continue
            if (
                persona_name is not None
                and data.get("persona_name") != persona_name
            ):
                continue
            matched.add(meta["doc_id"])
        return [row for row in rows if row["doc_id"] in matched]


__all__ = [
    "KnowledgeQueryUtils",
    "KnowledgeRetrieverMixin",
]
"""知识库检索模块公开 API"""
