"""记忆召回模块

提供 5 路召回（FTS5/向量/嵌入/实体/时间）+ RRF 融合的检索能力，
作为 Mixin 注入到 MemoryManager，依赖其 `_db`/`_embedding_dim` 状态。
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

from liuying.utils.log import logger

from ...models.memory_item import MemoryItem
from ._common import (
    _DEFAULT_PERSONA,
    _EMBEDDING_DIM,
    _EPISODIC_EXPIRE_DAYS,
    _RRF_K,
    _extract_entities_simple,
    _hash_bow_embedding,
)


class RecallMixin:
    """召回 Mixin

    提供 5 路召回与 RRF 融合能力，依赖宿主类的
    `_db`、`_embedding_dim`、`access` 等成员。
    """

    # 类型提示，由宿主类 MemoryManager 初始化
    _db: Any
    _embedding_dim: int = _EMBEDDING_DIM

    async def recall(
        self,
        user_id: str,
        query: str,
        group_id: str | None = None,
        top_k: int = 5,
        mode: str = "auto",
        persona_name: str = _DEFAULT_PERSONA,
    ) -> list[dict]:
        """记忆召回主入口

        参数:
            user_id: 用户ID
            query: 查询文本
            group_id: 群组ID
            top_k: 返回数量
            mode: 召回模式（auto/fast/deep）
            persona_name: bot人格名

        返回:
            list[dict]: 记忆列表，每项含 id/summary/content/score
        """
        if not query or not query.strip():
            return []
        try:
            # 5 路召回并行执行，避免串行 5x 耗时
            fts_task = self._search_fts(query, top_k * 3)
            vector_task = self._search_vector(query, top_k * 3)
            embedding_task = self._search_embedding(query, top_k * 3)
            entity_task = self._search_entity(query, top_k * 3)
            time_task = self._search_time(
                query,
                top_k * 3,
                user_id=user_id,
                group_id=group_id,
                persona_name=persona_name,
            )
            fts_res, vec_res, emb_res, ent_res, time_res = (
                await asyncio.gather(
                    fts_task,
                    vector_task,
                    embedding_task,
                    entity_task,
                    time_task,
                )
            )
            candidates: dict[str, list[tuple[int, float]]] = {
                "fts": fts_res,
                "vector": vec_res,
                "embedding": emb_res,
                "entity": ent_res,
                "time": time_res,
            }
            fused = self._fuse_recall(candidates)
            if not fused:
                return []
            # 批量查询记忆项，避免 N+1 查询
            top_ids = [mid for mid, _ in fused[:top_k]]
            memories = await MemoryItem.filter(id__in=top_ids).all()
            mem_by_id = {m.id: m for m in memories}
            results = []
            for mid, score in fused[:top_k]:
                memory = mem_by_id.get(mid)
                # 按 user_id 与 persona_name 双重过滤，确保人设间记忆隔离
                if (
                    memory
                    and memory.user_id == user_id
                    and memory.persona_name == persona_name
                ):
                    results.append(
                        {
                            "id": memory.id,
                            "summary": memory.summary,
                            "content": memory.content,
                            "tier": memory.tier,
                            "score": score,
                        }
                    )
                    await self.access(mid)
            return results
        except Exception as e:
            logger.warning(
                f"记忆召回失败，降级到无记忆模式: {e}",
                command="AI",
                e=e,
            )
            return []

    async def access(self, memory_id: int) -> None:
        """访问记忆

        参数:
            memory_id: 记忆ID
        """
        memory = await MemoryItem.filter(id=memory_id).first()
        if not memory:
            return
        memory.access_count += 1
        memory.last_access_time = datetime.now()
        await memory.save(
            update_fields=["access_count", "last_access_time"]
        )

    async def _search_fts(
        self, query: str, limit: int
    ) -> list[tuple[int, float]]:
        """FTS5全文检索

        参数:
            query: 查询文本
            limit: 返回上限

        返回:
            list[tuple[int, float]]: (memory_id, score) 列表
        """
        return await self._db.fts.search(query, limit)

    async def _search_vector(
        self, query: str, limit: int
    ) -> list[tuple[int, float]]:
        """向量检索

        参数:
            query: 查询文本
            limit: 返回上限

        返回:
            list[tuple[int, float]]: (memory_id, score) 列表
        """
        query_vec = _hash_bow_embedding(query, self._embedding_dim)
        return await self._db.vector.vector_search(query_vec, limit)

    async def _search_embedding(
        self, query: str, limit: int
    ) -> list[tuple[int, float]]:
        """主嵌入向量检索

        与 _search_vector 区别：在主嵌入表（search_embeddings）中检索，
        而非分块表（search_vector_chunks）。

        参数:
            query: 查询文本
            limit: 返回上限

        返回:
            list[tuple[int, float]]: (memory_id, score) 列表
        """
        query_vec = _hash_bow_embedding(query, self._embedding_dim)
        return await self._db.vector.embedding_search(query_vec, limit)

    async def _search_time(
        self,
        query: str,
        limit: int,
        user_id: str | None = None,
        group_id: str | None = None,
        persona_name: str = _DEFAULT_PERSONA,
    ) -> list[tuple[int, float]]:
        """时间检索

        返回最近创建的记忆（按时间倒序），用于补充时间维度的召回。
        同时按 persona_name 过滤，确保人设间记忆隔离。

        参数:
            query: 查询文本（未使用，保留签名以便扩展）
            limit: 返回上限
            user_id: 用户ID，用于过滤
            group_id: 群组ID，用于过滤
            persona_name: bot人格名，用于过滤

        返回:
            list[tuple[int, float]]: (memory_id, score) 列表，按时间倒序
        """
        cutoff = datetime.now() - timedelta(days=_EPISODIC_EXPIRE_DAYS)
        query_stmt = MemoryItem.filter(create_time__gt=cutoff)
        if user_id:
            query_stmt = query_stmt.filter(user_id=user_id)
        if group_id:
            query_stmt = query_stmt.filter(group_id=group_id)
        query_stmt = query_stmt.filter(persona_name=persona_name)
        memories = await query_stmt.order_by(
            "-create_time"
        ).limit(limit).all()
        if not memories:
            return []
        max_count = float(len(memories))
        return [
            (m.id, (len(memories) - idx) / max_count)
            for idx, m in enumerate(memories)
        ]

    async def _search_entity(
        self, query: str, limit: int
    ) -> list[tuple[int, float]]:
        """实体检索

        参数:
            query: 查询文本
            limit: 返回上限

        返回:
            list[tuple[int, float]]: (memory_id, score) 列表
        """
        entities = _extract_entities_simple(query)
        entity_names = [e["name"] for e in entities]
        return await self._db.entity.entity_search(entity_names, limit)

    def _fuse_recall(
        self,
        candidates: dict[str, list[tuple[int, float]]],
        rrf_k: int = _RRF_K,
    ) -> list[tuple[int, float]]:
        """RRF融合多路召回结果

        参数:
            candidates: 各路召回结果 {source: [(id, score)]}
            rrf_k: RRF参数

        返回:
            list[tuple[int, float]]: 融合后的 (id, score) 列表
        """
        scores: dict[int, float] = {}
        for _source, results in candidates.items():
            for rank, (mem_id, _score) in enumerate(results):
                rrf_score = 1.0 / (rrf_k + rank + 1)
                scores[mem_id] = scores.get(mem_id, 0.0) + rrf_score
        fused = sorted(
            scores.items(), key=lambda x: x[1], reverse=True
        )
        return fused
