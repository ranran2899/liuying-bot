"""记忆巩固与衰减模块

提供记忆巩固（reinforce/consolidate）与过期衰减（decay_expired）能力，
作为组合式内部服务由 MemoryManager 构造并注入依赖。
"""

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from liuying.utils.log import logger

from ..core.knowledge_db import KnowledgeBase
from ..core.llm import llm_helper
from ..core.llm.model_router import ROLE_INTENT, model_router
from ..core.memory._common import (
    _DEFAULT_PERSONA,
    _EPISODIC_EXPIRE_DAYS,
    _REINFORCE_THRESHOLD,
    _WORKING_EXPIRE_HOURS,
)
from ..models.conversation_record import ConversationRecord
from ..models.memory_item import MemoryItem


class MemoryConsolidationService:
    """巩固与衰减服务

    提供记忆强化、晋升、衰减与摘要巩固能力。
    依赖由构造器显式注入；写入新记忆通过注入的
    add_memory 回调委托给 MemoryManager.add。
    """

    def __init__(
        self,
        db: KnowledgeBase,
        add_memory: Callable[..., Awaitable[int]],
    ) -> None:
        """初始化巩固服务

        参数:
            db: 知识库检索实例
            add_memory: 记忆写入回调（MemoryManager.add）
        """
        self._db = db
        self._add_memory = add_memory

    async def reinforce(self, memory_id: int) -> None:
        """巩固记忆

        reinforcement_count +1，达到阈值时晋升tier。

        参数:
            memory_id: 记忆ID
        """
        memory = await MemoryItem.filter(id=memory_id).first()
        if not memory:
            return
        memory.reinforcement_count += 1
        memory.access_count += 1
        memory.last_access_time = datetime.now()
        if (
            memory.reinforcement_count >= _REINFORCE_THRESHOLD
            and memory.tier in ("working", "episodic")
        ):
            memory.tier = "semantic"
            memory.is_protected = True
        await memory.save(
            update_fields=[
                "reinforcement_count",
                "access_count",
                "last_access_time",
                "tier",
                "is_protected",
            ]
        )

    async def decay_expired(self) -> int:
        """衰减过期记忆

        working层24h未巩固降级episodic，
        episodic层30天无reinforcement硬删（非受保护）。

        返回:
            int: 处理的记忆数量
        """
        now = datetime.now()
        count = 0

        # 批量降级 working -> episodic，避免循环 save 的 N+1 问题
        working_expired_ids = await MemoryItem.filter(
            tier="working",
            expire_time__lt=now,
        ).values_list("id", flat=True)
        if working_expired_ids:
            await MemoryItem.filter(
                id__in=working_expired_ids
            ).update(tier="episodic", expire_time=None)
            count += len(working_expired_ids)

        # 批量硬删过期 episodic，向量索引需逐条调用外部 API（无法批量），
        # DB 侧用批量 delete 收尾
        episodic_cutoff = now - timedelta(days=_EPISODIC_EXPIRE_DAYS)
        episodic_expired = await MemoryItem.filter(
            tier="episodic",
            is_protected=False,
            reinforcement_count=0,
            create_time__lt=episodic_cutoff,
        ).all()
        if episodic_expired:
            for memory in episodic_expired:
                try:
                    await self._db.delete_document(memory.id)
                except Exception as e:
                    logger.debug(
                        f"删除记忆索引失败: {e}",
                        command="AI",
                        e=e,
                    )
            await MemoryItem.filter(
                id__in=[m.id for m in episodic_expired]
            ).delete()
            count += len(episodic_expired)

        if count > 0:
            logger.info(
                f"记忆衰减处理完成，处理{count}条",
                command="AI",
            )
        return count

    async def consolidate(
        self,
        user_id: str,
        group_id: str | None = None,
        window_hours: int = _WORKING_EXPIRE_HOURS,
        persona_name: str = _DEFAULT_PERSONA,
    ) -> int:
        """巩固记忆

        将窗口内的原始消息摘要成daily summary，
        原始条目reinforcement_count +1并降为background层。

        参数:
            user_id: 用户ID
            group_id: 群组ID
            window_hours: 时间窗口（小时）
            persona_name: bot人格名

        返回:
            int: 巩固的记忆数量
        """
        cutoff = datetime.now() - timedelta(hours=window_hours)
        records_query = ConversationRecord.filter(
            user_id=user_id,
            persona_name=persona_name,
            create_time__gt=cutoff,
        )
        if group_id:
            records_query = records_query.filter(group_id=group_id)
        records = await records_query.order_by("create_time").all()
        if len(records) < 5:
            return 0
        history = "\n".join(
            f"{r.role}: {r.content}" for r in records[-20:]
        )
        prompt = (
            "请将以下对话记录摘要成一段简洁的记忆。\n\n"
            "对话记录：\n"
            f"{history}\n\n"
            "要求：\n"
            "1. 提取关键信息和事件\n"
            "2. 保留重要细节\n"
            "3. 不超过100字\n"
            "4. 只返回摘要文本"
        )
        try:
            role = model_router.resolve(ROLE_INTENT)
            summary = await llm_helper.chat_text(
                [{"role": "user", "content": prompt}],
                model=role.model or None,
                options=role.apply_to_options({"temperature": 0.3}),
                provider_name=role.provider or None,
            )
            await self._add_memory(
                user_id=user_id,
                content=history[:500],
                summary=summary,
                group_id=group_id,
                tier="semantic",
                salience=0.8,
                persona_name=persona_name,
            )
            # 批量降级 working -> background，并用 SQL 原子递增
            # reinforcement_count，避免循环 save 的 N+1 问题
            consolidated_ids = await MemoryItem.filter(
                user_id=user_id,
                persona_name=persona_name,
                tier="working",
                create_time__lt=cutoff,
            ).values_list("id", flat=True)
            if consolidated_ids:
                await MemoryItem.filter(
                    id__in=consolidated_ids
                ).update(
                    reinforcement_count=(
                        MemoryItem.reinforcement_count + 1
                    ),
                    tier="background",
                )
            logger.info(
                f"记忆巩固完成: {user_id} persona={persona_name}",
                command="AI",
            )
            return len(consolidated_ids)
        except Exception as e:
            logger.warning(
                f"记忆巩固失败: {e}", command="AI", e=e
            )
            return 0
