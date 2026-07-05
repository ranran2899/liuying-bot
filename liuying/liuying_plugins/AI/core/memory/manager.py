"""记忆系统

4层记忆管理（working/episodic/semantic/background）+
5路召回（FTS5/向量/嵌入/实体/时间）+ RRF融合 +
记忆衰减与巩固。
所有记忆绑定 persona_name，实现人设间记忆数据隔离。
"""

import asyncio

from liuying.services.liuying_db import search_manager
from liuying.utils.log import logger

from ...models.memory_item import MemoryItem
from ._common import (
    _DEFAULT_PERSONA,
    _EMBEDDING_DIM,
    _extract_entities_simple,
    _hash_bow_embedding,
)
from .consolidation import ConsolidationMixin
from .recall import RecallMixin


class MemoryManager(RecallMixin, ConsolidationMixin):
    """记忆管理器

    管理4层记忆，提供5路召回+RRF融合的检索能力。
    所有记忆绑定 persona_name，实现人设间数据隔离。
    """

    def __init__(self, db=None) -> None:
        """初始化记忆管理器

        参数:
            db: SearchManager实例，None时用单例
        """
        self._db = db or search_manager
        self._embedding_dim = _EMBEDDING_DIM

    async def add(
        self,
        user_id: str,
        content: str,
        summary: str | None = None,
        group_id: str | None = None,
        tier: str = "working",
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
        return memory.id

    async def _index_memory(self, memory: MemoryItem) -> None:
        """为记忆建立检索索引（原子写入）

        通过 SearchManager.upsert_document 在单个事务内同时写入
        FTS、向量、实体数据，保证一致性。
        metadata 中包含 persona_name 以支持按人格过滤。

        参数:
            memory: 记忆项
        """
        search_text = f"{memory.summary} {memory.content}"
        embedding = _hash_bow_embedding(search_text, self._embedding_dim)
        entities = _extract_entities_simple(search_text)
        await self._db.upsert_document(
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
            model_version="hash_bow",
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
        memories = await self.recall(
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

        同时清理数据库记忆项、搜索索引与全局搜索表。

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
