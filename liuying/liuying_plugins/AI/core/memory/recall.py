"""记忆召回模块

提供 5 路召回（FTS5/向量/嵌入/实体/时间）+ RRF 融合的检索能力，
作为组合式内部服务由 MemoryManager 构造并注入依赖。
融合后通过 search_ranker 进行综合重排序，提升召回质量。
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

from liuying.utils.log import logger

from ...agent.intent.knowledge_rewrite import rewrite_query
from ...config import get_config
from ...models.memory_item import MemoryItem
from ..knowledge_db import KnowledgeBase
from ._common import (
    _DEFAULT_PERSONA,
    _EPISODIC_EXPIRE_DAYS,
    _RRF_K,
    MemoryEmbeddingUtils,
)
from .embedding_service import EmbeddingService
from .search_ranker import search_ranker


class MemoryRecallService:
    """记忆召回服务

    提供 5 路召回与 RRF 融合能力，依赖由构造器显式注入。
    """

    def __init__(
        self,
        db: KnowledgeBase,
        embedding_service: EmbeddingService,
    ) -> None:
        """初始化召回服务

        参数:
            db: 知识库检索实例
            embedding_service: 嵌入服务
        """
        self._db = db
        self._embedding_service = embedding_service

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

        5路召回 + RRF融合 + search_ranker综合重排序。
        向量/嵌入双路将 user_id 与 persona_name 下推到检索层
        过滤，避免候选被其他用户/人格的记忆挤占。

        检索意图改写（KNOWLEDGE_QUERY_REWRITE_ENABLED）默认关闭：
        每条消息热路径串行一次 LLM 改写开销过大，
        仅建议在深度召回场景手动开启该配置。

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
        # 检索意图改写：LLM识别梗/黑话/缩写补出正式名，提升召回准确率
        if get_config("KNOWLEDGE_QUERY_REWRITE_ENABLED", False):
            query = await rewrite_query(query)
        # 查询向量只计算一次，向量/嵌入双路共用，
        # 避免同一查询重复调用嵌入API
        try:
            query_vec: list[float] | None = (
                await self._embedding_service.embed_text(query)
            )
        except Exception as e:
            logger.warning(
                f"查询嵌入失败，向量双路降级为空: {e}",
                command="AI",
                e=e,
            )
            query_vec = None
        limit = top_k * 3
        # 5 路召回并行执行，避免串行 5x 耗时
        fts_res, vec_res, emb_res, ent_res, time_res = (
            await asyncio.gather(
                self._search_fts(query, limit),
                self._search_vector(
                    query_vec, limit, user_id, persona_name
                ),
                self._search_embedding(
                    query_vec, limit, user_id, persona_name
                ),
                self._search_entity(query, limit),
                self._search_time(
                    query,
                    limit,
                    user_id=user_id,
                    group_id=group_id,
                    persona_name=persona_name,
                ),
                return_exceptions=True,
            )
        )
        # 单路召回失败（嵌入API/DB异常等）不应中断整体回复，
        # 逐路降级为空，保留其余路径的召回结果
        raw_results = {
            "fts": fts_res,
            "vector": vec_res,
            "embedding": emb_res,
            "entity": ent_res,
            "time": time_res,
        }
        candidates: dict[str, list[tuple[int, float]]] = {}
        for name, result in raw_results.items():
            if isinstance(result, Exception):
                logger.warning(
                    f"记忆召回 {name} 路失败，降级为空: {result}",
                    command="AI",
                )
                continue
            candidates[name] = result
        fused = self._fuse_recall(candidates)
        if not fused:
            return []
        # 批量查询记忆项，避免 N+1 查询
        # 取 top_k * 2 候选用于重排序后再截断
        candidate_count = min(len(fused), top_k * 2)
        top_ids = [mid for mid, _ in fused[:candidate_count]]
        memories = await MemoryItem.filter(id__in=top_ids).all()
        mem_by_id = {m.id: m for m in memories}

        # 构建重排序候选列表，按 user_id 与 persona_name 双重过滤
        rerank_list: list[tuple[float, MemoryItem]] = []
        for mid, rrf_score in fused[:candidate_count]:
            memory = mem_by_id.get(mid)
            if (
                memory
                and memory.user_id == user_id
                and memory.persona_name == persona_name
            ):
                rerank_list.append((rrf_score, memory))

        # search_ranker 综合重排序
        scored: list[tuple[float, MemoryItem]] = []
        for rrf_score, memory in rerank_list:
            payload = self._memory_to_rank_payload(memory)
            final_score = search_ranker.rank_memory_payload(
                payload,
                query=query,
                base_score=rrf_score,
                requested_group_id=group_id or "",
                requested_user_id=user_id,
            )
            scored.append((final_score, memory))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        accessed_ids: list[int] = []
        for final_score, memory in scored[:top_k]:
            results.append(
                {
                    "id": memory.id,
                    "summary": memory.summary,
                    "content": memory.content,
                    "tier": memory.tier,
                    "score": final_score,
                }
            )
            accessed_ids.append(memory.id)
        # 批量更新访问计数，避免N+1查询
        if accessed_ids:
            now = datetime.now()
            await MemoryItem.filter(id__in=accessed_ids).update(
                access_count=MemoryItem.access_count + 1,
                last_access_time=now,
            )
        return results

    @staticmethod
    def _memory_to_rank_payload(
        memory: MemoryItem,
    ) -> dict[str, Any]:
        """将MemoryItem转换为search_ranker所需的payload字典

        参数:
            memory: 记忆项对象

        返回:
            dict: rank_memory_payload 所需的字段字典
        """
        return {
            "confidence": memory.confidence,
            "stability": memory.stability,
            "salience": memory.salience,
            "reinforcement_count": memory.reinforcement_count,
            "access_count": memory.access_count,
            "superseded_by": memory.superseded_by or "",
            "tier": memory.tier,
            "group_id": memory.group_id or "",
            "user_id": memory.user_id,
            "create_time": (
                memory.create_time.timestamp()
                if memory.create_time
                else 0.0
            ),
            "expire_time": (
                memory.expire_time.timestamp()
                if memory.expire_time
                else 0.0
            ),
            "last_access_time": (
                memory.last_access_time.timestamp()
                if memory.last_access_time
                else 0.0
            ),
        }

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
        return await self._db.search_fts(query, limit)

    async def _search_vector(
        self,
        query_vec: list[float] | None,
        limit: int,
        user_id: str | None = None,
        persona_name: str | None = None,
    ) -> list[tuple[int, float]]:
        """向量检索

        将 user_id 与 persona_name 下推到检索层过滤，
        避免候选被其他用户/人格的记忆挤占。

        参数:
            query_vec: 预计算的查询向量，None时跳过
            limit: 返回上限
            user_id: 用户ID，用于归属过滤
            persona_name: bot人格名，用于归属过滤

        返回:
            list[tuple[int, float]]: (memory_id, score) 列表
        """
        if query_vec is None:
            return []
        return await self._db.search_vector(
            query_vec,
            limit,
            self._embedding_service.model_version,
            user_id=user_id,
            persona_name=persona_name,
        )

    async def _search_embedding(
        self,
        query_vec: list[float] | None,
        limit: int,
        user_id: str | None = None,
        persona_name: str | None = None,
    ) -> list[tuple[int, float]]:
        """主嵌入向量检索

        与 _search_vector 区别：在主嵌入表（search_embeddings）中检索，
        而非分块表（search_vector_chunks）。
        同样将 user_id 与 persona_name 下推到检索层过滤。

        参数:
            query_vec: 预计算的查询向量，None时跳过
            limit: 返回上限
            user_id: 用户ID，用于归属过滤
            persona_name: bot人格名，用于归属过滤

        返回:
            list[tuple[int, float]]: (memory_id, score) 列表
        """
        if query_vec is None:
            return []
        return await self._db.search_embedding(
            query_vec,
            limit,
            self._embedding_service.model_version,
            user_id=user_id,
            persona_name=persona_name,
        )

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
        entities = MemoryEmbeddingUtils.extract_entities_simple(query)
        entity_names = [e["name"] for e in entities]
        return await self._db.search_entity(entity_names, limit)

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
