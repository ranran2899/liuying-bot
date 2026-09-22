"""记忆系统

4层记忆管理（working/episodic/semantic/background）+
5路召回（FTS5/向量/嵌入/实体/时间）+ RRF融合 +
记忆衰减与巩固 + 记忆进化（覆盖/合并/巩固/冲突）。
所有记忆绑定 persona_name，实现人设间记忆数据隔离。
"""

import asyncio
from collections.abc import Coroutine
from typing import Any

from liuying.utils.log import logger

from ...agent.intent.memory_consolidate import MemoryConsolidationService
from ...agent.intent.memory_evolve import MemoryEvolveService
from ...config import get_config
from ...models.memory_item import MemoryItem, MemoryTier
from ..knowledge_index import knowledge_base
from ._common import (
    _DEFAULT_PERSONA,
    _WORKING_EXPIRE_HOURS,
    MemoryEmbeddingUtils,
)
from .background_intelligence import background_intelligence
from .embedding_service import EmbeddingService
from .recall import MemoryRecallItem, MemoryRecallService

_BG_SEMAPHORE = asyncio.Semaphore(4)
"""后台任务并发信号量

限制记忆进化与后台智能任务的总并发数为 4：
每次 add 都会派生两个后台 Task（evolve 与
background_intelligence），高频写入时若无上限会
造成任务无限堆积，拖垮事件循环并放大 LLM 调用压力。
"""


class MemoryManager:
    """记忆管理器

    管理4层记忆，提供5路召回+RRF融合的检索能力。
    所有记忆绑定 persona_name，实现人设间数据隔离。
    集成记忆进化引擎，写入后自动判断与旧记忆的关系。
    召回/巩固/进化能力由组合式内部服务提供，
    依赖通过构造器显式注入。
    """

    def __init__(self, db=None) -> None:
        """初始化记忆管理器

        参数:
            db: KnowledgeBase实例，None时用单例
        """
        self._db = db or knowledge_base
        self._embedding_service = EmbeddingService()
        self._embedding_dim = self._embedding_service.embedding_dim
        self._bg_tasks: set[asyncio.Task] = set()
        self._recall_service = MemoryRecallService(
            self._db, self._embedding_service
        )
        self._consolidation_service = MemoryConsolidationService(
            self._db, add_memory=self.add
        )
        self._evolve_service = MemoryEvolveService(
            self._recall_service, self._consolidation_service
        )

    async def recall(
        self,
        user_id: str,
        query: str,
        group_id: str | None = None,
        top_k: int = 5,
        mode: str = "auto",
        persona_name: str = _DEFAULT_PERSONA,
    ) -> list[MemoryRecallItem]:
        """记忆召回（委托召回服务）

        参数:
            user_id: 用户ID
            query: 查询文本
            group_id: 群组ID
            top_k: 返回数量
            mode: 召回模式（auto/fast/deep）
            persona_name: bot人格名

        返回:
            list[dict]: 记忆列表
        """
        return await self._recall_service.recall(
            user_id=user_id,
            query=query,
            group_id=group_id,
            top_k=top_k,
            mode=mode,
            persona_name=persona_name,
        )

    async def decay_expired(self) -> int:
        """衰减过期记忆（委托巩固服务）

        返回:
            int: 处理的记忆数量
        """
        return await self._consolidation_service.decay_expired()

    async def consolidate(
        self,
        user_id: str,
        group_id: str | None = None,
        window_hours: int = _WORKING_EXPIRE_HOURS,
        persona_name: str = _DEFAULT_PERSONA,
    ) -> int:
        """巩固记忆（委托巩固服务）

        参数:
            user_id: 用户ID
            group_id: 群组ID
            window_hours: 时间窗口（小时）
            persona_name: bot人格名

        返回:
            int: 巩固的记忆数量
        """
        return await self._consolidation_service.consolidate(
            user_id=user_id,
            group_id=group_id,
            window_hours=window_hours,
            persona_name=persona_name,
        )

    async def add(
        self,
        user_id: str,
        content: str,
        summary: str | None = None,
        group_id: str | None = None,
        tier: str = MemoryTier.WORKING,
        topic_tags: list[str] | None = None,
        entity_tags: list[str] | None = None,
        salience: float = 0.5,
        persona_name: str = _DEFAULT_PERSONA,
    ) -> int:
        """添加记忆项

        参数:
            user_id: 用户ID
            content: 原始内容
            summary: 摘要，None时用content
            group_id: 群组ID
            tier: 记忆层级
            topic_tags: 话题标签
            entity_tags: 实体标签
            salience: 重要性
            persona_name: bot人格名

        返回:
            int: 记忆ID
        """
        use_summary = summary or content
        memory = await MemoryItem.add_memory(
            user_id=user_id,
            content=content,
            summary=use_summary,
            group_id=group_id,
            tier=tier,
            topic_tags=topic_tags,
            entity_tags=entity_tags,
            salience=salience,
            persona_name=persona_name,
        )
        try:
            await self._index_memory(memory)
        except Exception as e:
            # 索引失败时记忆写入DB但不可检索，需 warning 提示运维
            logger.warning(
                f"索引记忆失败（记忆已写入但不可检索）: {e}",
                command="AI",
                e=e,
            )
        # 记忆进化：后台异步执行，不阻塞写入返回
        # 持有Task强引用防止被GC回收导致任务静默取消
        if get_config("MEMORY_EVOLVE_ENABLED", True):
            evolve_task = asyncio.create_task(
                self._run_bg_limited(
                    self._safe_evolve(
                        user_id=user_id,
                        new_memory_id=memory.id,
                        new_summary=use_summary,
                        group_id=group_id,
                        persona_name=persona_name,
                    )
                )
            )
            self._bg_tasks.add(evolve_task)
            evolve_task.add_done_callback(self._bg_tasks.discard)
            # 后台智能：防抖触发去重/晶体化
            bg_task = asyncio.create_task(
                self._run_bg_limited(
                    background_intelligence.notify_memory_added(
                        user_id=user_id,
                        memory_id=memory.id,
                        summary=use_summary,
                        group_id=group_id,
                        persona_name=persona_name,
                    )
                )
            )
            self._bg_tasks.add(bg_task)
            bg_task.add_done_callback(self._bg_tasks.discard)
        return memory.id

    @staticmethod
    async def _run_bg_limited(
        coro: Coroutine[Any, Any, None],
    ) -> None:
        """在信号量限流下执行后台协程

        通过 _BG_SEMAPHORE 限制后台任务总并发数，
        防止高频写入时任务堆积拖垮事件循环。
        同时兜底吞掉协程异常，避免未检索的 Task 异常告警。

        参数:
            coro: 待执行的后台协程
        """
        async with _BG_SEMAPHORE:
            try:
                await coro
            except Exception as e:
                logger.debug(
                    f"后台任务执行失败: {e}", command="AI", e=e
                )

    async def _safe_evolve(
        self,
        user_id: str,
        new_memory_id: int,
        new_summary: str,
        group_id: str | None,
        persona_name: str,
    ) -> None:
        """安全执行记忆进化（吞异常，不阻塞主流程）

        参数:
            user_id: 用户ID
            new_memory_id: 新记忆ID
            new_summary: 新记忆摘要
            group_id: 群组ID
            persona_name: bot人格名
        """
        try:
            await self._evolve_service.evolve_memory(
                user_id=user_id,
                new_memory_id=new_memory_id,
                new_summary=new_summary,
                group_id=group_id,
                persona_name=persona_name,
            )
        except Exception as e:
            logger.debug(
                f"记忆进化后台任务失败: {e}",
                command="AI",
                e=e,
            )

    async def _index_memory(self, memory: MemoryItem) -> None:
        """为记忆建立检索索引（原子写入）

        通过 KnowledgeBase.index_document 在单个事务内同时写入
        FTS、向量、实体数据，保证一致性。
        metadata 中包含 persona_name 以支持按人格过滤。

        参数:
            memory: 记忆项
        """
        search_text = f"{memory.summary} {memory.content}"
        embedding = await self._embedding_service.embed_text(
            search_text
        )
        entities = MemoryEmbeddingUtils.extract_entities_simple(search_text)
        await self._db.index_document(
            doc_id=memory.id,
            text=search_text,
            embedding=embedding,
            chunks=[{"vector": embedding, "salience": memory.salience}],
            entities=entities or None,
            metadata={
                "user_id": memory.user_id,
                "group_id": memory.group_id,
                "tier": memory.tier,
                "persona_name": memory.persona_name,
            },
            model_version=self._embedding_service.model_version,
        )

    async def get_memory_summary(
        self,
        user_id: str,
        group_id: str | None = None,
        limit: int = 10,
        persona_name: str = _DEFAULT_PERSONA,
    ) -> list[dict]:
        """获取用户记忆摘要

        参数:
            user_id: 用户ID
            group_id: 群组ID
            limit: 返回数量
            persona_name: bot人格名

        返回:
            list[dict]: 记忆摘要列表
        """
        query = MemoryItem.filter(
            user_id=user_id, persona_name=persona_name
        )
        if group_id:
            query = query.filter(group_id=group_id)
        memories = await query.order_by("-create_time").limit(limit).all()
        return [
            {
                "id": m.id,
                "summary": m.summary,
                "tier": m.tier,
                "create_time": m.create_time.strftime("%Y-%m-%d %H:%M")
                if m.create_time
                else "",
            }
            for m in memories
        ]

    async def build_memory_prompt(
        self,
        user_id: str,
        query: str,
        group_id: str | None = None,
        top_k: int = 5,
        persona_name: str = _DEFAULT_PERSONA,
    ) -> str:
        """构建记忆上下文提示

        参数:
            user_id: 用户ID
            query: 当前查询
            group_id: 群组ID
            top_k: 召回数量
            persona_name: bot人格名

        返回:
            str: 记忆上下文提示文本
        """
        memories = await self._recall_service.recall(
            user_id,
            query,
            group_id,
            top_k=top_k,
            persona_name=persona_name,
        )
        if not memories:
            return ""
        lines = ["\n\n[相关记忆]"]
        for mem in memories:
            lines.append(f"- {mem['summary']}")
        return "\n".join(lines)

    async def clear_user_memory(
        self,
        user_id: str,
        persona_name: str = _DEFAULT_PERSONA,
        group_id: str | None = None,
    ) -> int:
        """清空指定用户指定人格的记忆数据

        同时清理数据库记忆项与搜索索引，确保人设间记忆隔离。

        参数:
            user_id: 用户ID
            persona_name: bot人格名
            group_id: 群组ID，None时清除所有群组

        返回:
            int: 清除的记忆数量
        """
        ids = await MemoryItem.clear_by_user_persona(
            user_id=user_id,
            persona_name=persona_name,
            group_id=group_id,
        )
        if ids:
            await asyncio.gather(
                *[self._safe_delete_index(mid) for mid in ids],
                return_exceptions=False,
            )
        logger.info(
            f"清空用户记忆: user={user_id} persona={persona_name} "
            f"count={len(ids)}",
            command="AI",
        )
        return len(ids)

    async def clear_all_memory(self) -> int:
        """清空所有用户所有人格的记忆数据（管理员操作）

        同时清理数据库记忆项与全部搜索索引表。

        返回:
            int: 清除的记忆数量
        """
        ids = await MemoryItem.clear_all_memories()
        # 清空全部搜索索引表（记忆索引与记忆项一一对应）
        try:
            await self._db.clear_all()
        except Exception as e:
            logger.warning(
                f"清空搜索索引失败: {e}", command="AI", e=e
            )
        logger.warning(
            f"全局清空所有记忆: count={len(ids)}",
            command="AI",
        )
        return len(ids)

    async def _safe_delete_index(self, doc_id: int) -> None:
        """安全删除搜索索引（吞异常）

        参数:
            doc_id: 文档ID
        """
        try:
            await self._db.delete_document(doc_id)
        except Exception as e:
            logger.debug(
                f"删除搜索索引失败 doc_id={doc_id}: {e}",
                command="AI",
                e=e,
            )


memory_manager = MemoryManager()
"""记忆管理器单例"""
