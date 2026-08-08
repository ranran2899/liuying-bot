"""记忆摘要器

定时将同用户同人格的多条工作记忆摘要为一条语义记忆，
原始工作记忆降级为背景层。与 consolidation.py 的区别：
consolidate 从 ConversationRecord 摘要；summarizer 从
MemoryItem 摘要，聚焦记忆库自身的层级晋升。
"""

from datetime import datetime, timedelta

from liuying.utils.log import logger

from ...models.memory_item import MemoryItem
from ..llm import llm_helper
from ._common import _DEFAULT_PERSONA

_BATCH_SIZE = 8
"""单批摘要的记忆数量"""

_MIN_MEMORIES_TO_SUMMARIZE = 3
"""触发摘要的最少记忆数量"""

_WORKING_AGE_HOURS = 6
"""工作记忆最小年龄（小时），低于此值不摘要"""


class MemorySummarizer:
    """记忆摘要器

    定时将工作记忆摘要为语义记忆，实现记忆层级晋升。
    """

    def __init__(self) -> None:
        """初始化记忆摘要器"""

    async def summarize_user_working_memories(
        self,
        user_id: str,
        group_id: str | None = None,
        persona_name: str = _DEFAULT_PERSONA,
    ) -> int:
        """摘要指定用户的工作记忆

        参数:
            user_id: 用户ID
            group_id: 群组ID
            persona_name: bot人格名

        返回:
            int: 摘要后生成的语义记忆数量
        """
        cutoff = datetime.now() - timedelta(
            hours=_WORKING_AGE_HOURS
        )
        query = MemoryItem.filter(
            user_id=user_id,
            persona_name=persona_name,
            tier="working",
            create_time__lt=cutoff,
        )
        if group_id:
            query = query.filter(group_id=group_id)
        memories = await query.order_by("create_time").limit(
            _BATCH_SIZE
        ).all()
        if len(memories) < _MIN_MEMORIES_TO_SUMMARIZE:
            return 0
        summary = await self._generate_summary(memories)
        if not summary:
            return 0
        await MemoryItem.add_memory(
            user_id=user_id,
            content=self._build_content(memories),
            summary=summary,
            group_id=group_id,
            tier="semantic",
            salience=0.8,
            is_protected=True,
            persona_name=persona_name,
        )
        for mem in memories:
            mem.tier = "background"
            mem.reinforcement_count += 1
            await mem.save(
                update_fields=["tier", "reinforcement_count"]
            )
        logger.info(
            f"记忆摘要完成: user={user_id} "
            f"persona={persona_name} "
            f"summarized={len(memories)}",
            command="AI",
        )
        return 1

    async def summarize_all_users(self) -> int:
        """摘要所有用户的工作记忆（定时任务入口）

        返回:
            int: 处理的用户数量
        """
        cutoff = datetime.now() - timedelta(
            hours=_WORKING_AGE_HOURS
        )
        recent_memories = await MemoryItem.filter(
            tier="working",
            create_time__lt=cutoff,
        ).all()
        user_keys: set[tuple[str, str, str | None]] = set()
        for mem in recent_memories:
            user_keys.add(
                (mem.user_id, mem.persona_name, mem.group_id)
            )
        count = 0
        for user_id, persona_name, group_id in user_keys:
            try:
                result = await self.summarize_user_working_memories(
                    user_id=user_id,
                    group_id=group_id,
                    persona_name=persona_name,
                )
                if result > 0:
                    count += 1
            except Exception as e:
                logger.debug(
                    f"用户记忆摘要失败: user={user_id} -> {e}",
                    command="AI",
                    e=e,
                )
        if count > 0:
            logger.info(
                f"全量记忆摘要完成: users={count}",
                command="AI",
            )
        return count

    async def _generate_summary(
        self, memories: list[MemoryItem]
    ) -> str:
        """使用 LLM 生成记忆摘要

        参数:
            memories: 待摘要的记忆列表

        返回:
            str: 摘要文本，失败返回空串
        """
        lines: list[str] = []
        for mem in memories:
            timestamp = (
                mem.create_time.strftime("%Y-%m-%d %H:%M")
                if mem.create_time
                else ""
            )
            lines.append(f"- [{timestamp}] {mem.summary}")
        joined = "\n".join(lines)
        prompt = (
            "请将以下多条短期记忆摘要为一条简洁的长期记忆。\n\n"
            "短期记忆列表：\n"
            f"{joined}\n\n"
            "要求：\n"
            "1. 提取关键信息和事件，去除重复内容\n"
            "2. 保留重要细节和时间线索\n"
            "3. 不超过150字\n"
            "4. 只返回摘要文本，不要任何解释"
        )
        try:
            summary = await llm_helper.chat_text(
                [{"role": "user", "content": prompt}],
                options={"temperature": 0.3},
            )
            return summary.strip()
        except Exception as e:
            logger.warning(
                f"LLM摘要生成失败: {e}", command="AI", e=e
            )
            return ""

    @staticmethod
    def _build_content(
        memories: list[MemoryItem],
    ) -> str:
        """构建语义记忆的原始内容（拼接来源摘要）

        参数:
            memories: 来源记忆列表

        返回:
            str: 拼接后的内容文本
        """
        parts: list[str] = []
        for mem in memories:
            parts.append(mem.summary)
        return " | ".join(parts)[:500]


memory_summarizer = MemorySummarizer()
"""记忆摘要器单例"""
