"""向量存储与检索管理器

提供文档向量嵌入存储、向量分块存储与余弦相似度检索能力。
基于 SQLite TEXT 字段 + JSON 序列化实现，零外部依赖。

注意：当前实现为 Python 全表扫描，适合中小规模数据（万级以下）。
若数据规模增长，可后续替换为 sqlite-vec 扩展或迁移至专用向量库。
"""

import json
import math

from sqlalchemy import text as sql_text

from ..session import session_manager


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
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


class VectorManager:
    """向量存储与检索管理器

    示例:
        ```python
        vec = VectorManager("default")
        await vec.store_embedding(1, [0.1, 0.2, ...], model_version="hash_bow")
        results = await vec.vector_search(query_vec, top_k=5)
        ```
    """

    __slots__ = ("_db_name",)

    def __init__(self, db_name: str = "default") -> None:
        """初始化向量管理器

        参数:
            db_name: 数据库名称，默认 'default'
        """
        self._db_name = db_name

    async def store_embedding(
        self,
        doc_id: int,
        embedding: list[float],
        model_version: str = "hash_bow",
    ) -> None:
        """存储嵌入向量

        参数:
            doc_id: 文档 ID
            embedding: 嵌入向量
            model_version: 模型版本标识
        """
        async with session_manager.get_session(self._db_name) as session:
            await session.execute(
                sql_text(
                    "INSERT OR REPLACE INTO search_embeddings"
                    "(doc_id, embedding, model_version, dim) "
                    "VALUES(:doc_id, :embedding, :model_version, :dim)"
                ),
                {
                    "doc_id": doc_id,
                    "embedding": json.dumps(embedding),
                    "model_version": model_version,
                    "dim": len(embedding),
                },
            )
            await session.commit()

    async def store_chunks(
        self,
        doc_id: int,
        chunks: list[dict],
    ) -> None:
        """存储分块向量

        参数:
            doc_id: 文档 ID
            chunks: 分块列表，每项含 vector/salience/confidence/model_version
        """
        async with session_manager.get_session(self._db_name) as session:
            await session.execute(
                sql_text("DELETE FROM search_vector_chunks WHERE doc_id = :doc_id"),
                {"doc_id": doc_id},
            )
            for idx, chunk in enumerate(chunks):
                vec = chunk.get("vector", [])
                await session.execute(
                    sql_text(
                        "INSERT INTO search_vector_chunks"
                        "(doc_id, chunk_index, vector, salience, confidence, "
                        "model_version, embedding_dim) "
                        "VALUES(:doc_id, :chunk_index, :vector, :salience, "
                        ":confidence, :model_version, :embedding_dim)"
                    ),
                    {
                        "doc_id": doc_id,
                        "chunk_index": idx,
                        "vector": json.dumps(vec),
                        "salience": chunk.get("salience", 0.5),
                        "confidence": chunk.get("confidence", 0.5),
                        "model_version": chunk.get("model_version", "hash_bow"),
                        "embedding_dim": len(vec),
                    },
                )
            await session.commit()

    async def vector_search(
        self,
        query_vec: list[float],
        top_k: int = 10,
    ) -> list[tuple[int, float]]:
        """向量余弦相似度检索

        全表扫描所有分块向量，计算余弦相似度后取 TopK。

        参数:
            query_vec: 查询向量
            top_k: 返回条数上限

        返回:
            list[tuple[int, float]]: (doc_id, similarity) 列表，按相似度降序
        """
        async with session_manager.get_session(self._db_name) as session:
            result = await session.execute(
                sql_text("SELECT doc_id, vector FROM search_vector_chunks")
            )
            rows = result.fetchall()
        if not rows:
            return []
        scored: list[tuple[int, float]] = []
        for row in rows:
            doc_id = row[0]
            try:
                vec = json.loads(row[1])
            except (json.JSONDecodeError, TypeError):
                continue
            sim = cosine_similarity(query_vec, vec)
            scored.append((doc_id, sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    async def embedding_search(
        self,
        query_vec: list[float],
        top_k: int = 10,
    ) -> list[tuple[int, float]]:
        """主向量嵌入相似度检索（基于 search_embeddings 表）

        与 ``vector_search`` 区别：在主向量表而非分块表中检索，
        适合不需要分块的场景。

        参数:
            query_vec: 查询向量
            top_k: 返回条数上限

        返回:
            list[tuple[int, float]]: (doc_id, similarity) 列表
        """
        async with session_manager.get_session(self._db_name) as session:
            result = await session.execute(
                sql_text("SELECT doc_id, embedding FROM search_embeddings")
            )
            rows = result.fetchall()
        if not rows:
            return []
        scored: list[tuple[int, float]] = []
        for row in rows:
            doc_id = row[0]
            try:
                vec = json.loads(row[1])
            except (json.JSONDecodeError, TypeError):
                continue
            sim = cosine_similarity(query_vec, vec)
            scored.append((doc_id, sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    async def get_embedding(self, doc_id: int) -> list[float] | None:
        """获取文档的主嵌入向量

        参数:
            doc_id: 文档 ID

        返回:
            list[float] | None: 嵌入向量，不存在返回 None
        """
        async with session_manager.get_session(self._db_name) as session:
            result = await session.execute(
                sql_text(
                    "SELECT embedding FROM search_embeddings WHERE doc_id = :doc_id"
                ),
                {"doc_id": doc_id},
            )
            row = result.fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return None

    async def delete(self, doc_id: int) -> None:
        """删除指定文档的所有向量数据

        参数:
            doc_id: 文档 ID
        """
        async with session_manager.get_session(self._db_name) as session:
            await session.execute(
                sql_text("DELETE FROM search_embeddings WHERE doc_id = :doc_id"),
                {"doc_id": doc_id},
            )
            await session.execute(
                sql_text("DELETE FROM search_vector_chunks WHERE doc_id = :doc_id"),
                {"doc_id": doc_id},
            )
            await session.commit()
