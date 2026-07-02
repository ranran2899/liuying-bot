"""记忆巩固与衰减模块

提供记忆巩固（reinforce/consolidate）与过期衰减（decay_expired）能力，
作为 Mixin 注入到 MemoryManager。
"""

from datetime import datetime, timedelta
from typing import Any

from liuying.utils.log import logger

from ...models.conversation_record import ConversationRecord
from ...models.memory_item import MemoryItem
from ._common import (
    _CONSOLIDATE_PROMPT,
    _DEFAULT_PERSONA,
    _EPISODIC_EXPIRE_DAYS,
    _REINFORCE_THRESHOLD,
    _WORKING_EXPIRE_HOURS,
)


class ConsolidationMixin:
    """巩固与衰减 Mixin

    提供记忆强化、晋升、衰减与摘要巩固能力。
    依赖宿主类的 `_db`、`_get_llm`、`add` 等成员。
    """

    # 类型提示，由宿主类 MemoryManager 初始化
    _db: Any

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

        working_expired = await MemoryItem.filter(
            tier="working",
        ).all()
        for memory in working_expired:
            if memory.expire_time and now > memory.expire_time:
                memory.tier = "episodic"
                memory.expire_time = None
                await memory.save(
                    update_fields=["tier", "expire_time"]
                )
                count += 1

        episodic_cutoff = now - timedelta(days=_EPISODIC_EXPIRE_DAYS)
        episodic_expired = await MemoryItem.filter(
            tier="episodic",
            is_protected=False,
        ).all()
        for memory in episodic_expired:
            if (
                memory.reinforcement_count == 0
                and memory.create_time < episodic_cutoff
            ):
                try:
                    await self._db.delete_document(memory.id)
                except Exception as e:
                    logger.debug(
                        f"删除记忆索引失败: {e}",
                        command="AI",
                        e=e,
                    )
                await memory.delete()
                count += 1

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
        prompt = _CONSOLIDATE_PROMPT.format(history=history)
        try:
            summary = await self._get_llm().chat_text(
                [{"role": "user", "content": prompt}],
                options={"temperature": 0.3},
            )
            await self.add(
                user_id=user_id,
                content=history[:500],
                summary=summary,
                group_id=group_id,
                tier="semantic",
                salience=0.8,
                persona_name=persona_name,
            )
            working_mems_query = MemoryItem.filter(
                user_id=user_id,
                persona_name=persona_name,
                tier="working",
            )
            working_mems = await working_mems_query.all()
            for mem in working_mems:
                if mem.create_time < cutoff:
                    mem.reinforcement_count += 1
                    mem.tier = "background"
                    await mem.save(
                        update_fields=["reinforcement_count", "tier"]
                    )
            logger.info(
                f"记忆巩固完成: {user_id} persona={persona_name}",
                command="AI",
            )
            return len(working_mems)
        except Exception as e:
            logger.warning(
                f"记忆巩固失败: {e}", command="AI", e=e
            )
            return 0
