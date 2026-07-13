"""记忆进化引擎

在新记忆写入后，自动判断其与同用户同人格的旧记忆的关系
（replaces/enriches/confirms/challenges），执行覆盖、合并、
巩固或冲突标记，实现记忆库的自动演化与去重。
作为 Mixin 注入到 MemoryManager，依赖宿主类的 `_db` 成员。
"""

from datetime import datetime
from typing import Any

from liuying.utils.log import logger

from ...models.memory_item import MemoryItem
from ..llm import llm_helper
from ._common import _DEFAULT_PERSONA

_RELATION_REPLACES = "replaces"
"""新记忆覆盖旧记忆"""

_RELATION_ENRICHES = "enriches"
"""新记忆补充旧记忆"""

_RELATION_CONFIRMS = "confirms"
"""新记忆确认旧记忆"""

_RELATION_CHALLENGES = "challenges"
"""新记忆与旧记忆矛盾"""

_RELATION_UNRELATED = "unrelated"
"""无关"""

_VALID_RELATIONS = frozenset(
    {
        _RELATION_REPLACES,
        _RELATION_ENRICHES,
        _RELATION_CONFIRMS,
        _RELATION_CHALLENGES,
        _RELATION_UNRELATED,
    }
)
"""有效关系类型集合"""

_MAX_CANDIDATES = 5
"""单次进化判断的候选旧记忆数量"""

_EVOLVE_PROMPT = """你是一个记忆关系判断助手。
请判断新记忆与旧记忆之间的关系，只输出以下五个英文单词之一：

- replaces: 新记忆完全覆盖旧记忆（旧信息已过时或被纠正）
- enriches: 新记忆补充旧记忆（两者可合并为更完整记录）
- confirms: 新记忆确认旧记忆（内容基本一致，巩固旧记忆）
- challenges: 新记忆与旧记忆矛盾（保留两者，标记冲突）
- unrelated: 两者无直接关系

旧记忆：
{old_summary}

新记忆：
{new_summary}

只输出一个英文单词，不要任何其他内容。"""

_MERGE_PROMPT = """请合并以下两条记忆为一条更完整的摘要，保留双方关键信息。

旧记忆：{old_summary}
新记忆：{new_summary}

要求：
1. 只输出合并后的摘要文本
2. 不超过100字
3. 不输出任何解释"""


class EvolveMixin:
    """记忆进化 Mixin

    提供新记忆与旧记忆关系判断及自动演化能力。
    依赖宿主类的 `_db`、`add`、`recall` 等成员。
    """

    # 类型提示，由宿主类 MemoryManager 初始化
    _db: Any
    _embedding_dim: int = 64

    async def evolve_memory(
        self,
        user_id: str,
        new_memory_id: int,
        new_summary: str,
        group_id: str | None = None,
        persona_name: str = _DEFAULT_PERSONA,
    ) -> str:
        """对新记忆执行进化判断

        召回同用户同人格的相关旧记忆，使用 LLM 判断关系，
        执行覆盖/合并/巩固/冲突标记。

        参数:
            user_id: 用户ID
            new_memory_id: 新记忆ID
            new_summary: 新记忆摘要
            group_id: 群组ID
            persona_name: bot人格名

        返回:
            str: 进化关系类型（replaces/enriches/confirms/challenges/unrelated）
        """
        try:
            candidates = await self._fetch_evolve_candidates(
                user_id=user_id,
                new_memory_id=new_memory_id,
                new_summary=new_summary,
                group_id=group_id,
                persona_name=persona_name,
            )
            if not candidates:
                return _RELATION_UNRELATED

            for old_mem in candidates:
                relation = await self._judge_relation(
                    old_summary=old_mem["summary"],
                    new_summary=new_summary,
                )
                if relation == _RELATION_UNRELATED:
                    continue
                await self._apply_relation(
                    relation=relation,
                    old_memory=old_mem,
                    new_memory_id=new_memory_id,
                    new_summary=new_summary,
                )
                logger.debug(
                    f"记忆进化: new={new_memory_id} "
                    f"old={old_mem['id']} relation={relation}",
                    command="AI",
                )
                return relation
            return _RELATION_UNRELATED
        except Exception as e:
            logger.warning(
                f"记忆进化失败: {e}", command="AI", e=e
            )
            return _RELATION_UNRELATED

    async def _fetch_evolve_candidates(
        self,
        user_id: str,
        new_memory_id: int,
        new_summary: str,
        group_id: str | None,
        persona_name: str,
    ) -> list[dict]:
        """召回进化候选旧记忆

        参数:
            user_id: 用户ID
            new_memory_id: 新记忆ID（排除自身）
            new_summary: 新记忆摘要（作为查询）
            group_id: 群组ID
            persona_name: bot人格名

        返回:
            list[dict]: 候选旧记忆列表
        """
        results = await self.recall(
            user_id=user_id,
            query=new_summary,
            group_id=group_id,
            top_k=_MAX_CANDIDATES,
            mode="fast",
            persona_name=persona_name,
        )
        candidates: list[dict] = []
        for r in results:
            if r.get("id") == new_memory_id:
                continue
            if r.get("tier") == "background":
                continue
            candidates.append(r)
        return candidates

    async def _judge_relation(
    self,
        old_summary: str,
        new_summary: str,
    ) -> str:
        """使用 LLM 判断新旧记忆关系

        参数:
            old_summary: 旧记忆摘要
            new_summary: 新记忆摘要

        返回:
            str: 关系类型
        """
        prompt = _EVOLVE_PROMPT.format(
            old_summary=old_summary,
            new_summary=new_summary,
        )
        try:
            _, content = await llm_helper.chat(
                [{"role": "user", "content": prompt}],
                options={"temperature": 0.0},
            )
            relation = content.strip().lower()
            if relation not in _VALID_RELATIONS:
                return _RELATION_UNRELATED
            return relation
        except Exception as e:
            logger.debug(
                f"关系判断失败: {e}", command="AI", e=e
            )
            return _RELATION_UNRELATED

    async def _apply_relation(
        self,
        relation: str,
        old_memory: dict,
        new_memory_id: int,
        new_summary: str,
    ) -> None:
        """根据关系类型执行进化操作

        参数:
            relation: 关系类型
            old_memory: 旧记忆字典
            new_memory_id: 新记忆ID
            new_summary: 新记忆摘要
        """
        old_id = old_memory.get("id")
        if old_id is None:
            return
        if relation == _RELATION_REPLACES:
            await self._mark_superseded(old_id, new_memory_id)
        elif relation == _RELATION_ENRICHES:
            await self._merge_memories(
                old_id, old_memory.get("summary", ""), new_summary
            )
        elif relation == _RELATION_CONFIRMS:
            await self.reinforce(old_id)
        elif relation == _RELATION_CHALLENGES:
            await self._mark_conflict(old_id, new_memory_id)

    async def _mark_superseded(
        self, old_id: int, new_id: int
    ) -> None:
        """标记旧记忆被新记忆覆盖

        参数:
            old_id: 旧记忆ID
            new_id: 新记忆ID
        """
        memory = await MemoryItem.filter(id=old_id).first()
        if not memory:
            return
        memory.superseded_by = new_id
        memory.tier = "background"
        memory.is_protected = False
        await memory.save(
            update_fields=["superseded_by", "tier", "is_protected"]
        )

    async def _merge_memories(
        self, old_id: int, old_summary: str, new_summary: str
    ) -> None:
        """合并新旧记忆摘要

        参数:
            old_id: 旧记忆ID
            old_summary: 旧记忆摘要
            new_summary: 新记忆摘要
        """
        prompt = _MERGE_PROMPT.format(
            old_summary=old_summary,
            new_summary=new_summary,
        )
        try:
            merged = await llm_helper.chat_text(
                [{"role": "user", "content": prompt}],
                options={"temperature": 0.3},
            )
            merged = merged.strip()
        except Exception as e:
            logger.debug(
                f"记忆合并失败: {e}", command="AI", e=e
            )
            return
        if not merged:
            return
        memory = await MemoryItem.filter(id=old_id).first()
        if not memory:
            return
        memory.summary = merged
        memory.reinforcement_count += 1
        memory.last_access_time = datetime.now()
        await memory.save(
            update_fields=[
                "summary",
                "reinforcement_count",
                "last_access_time",
            ]
        )

    async def _mark_conflict(
        self, old_id: int, new_id: int
    ) -> None:
        """标记新旧记忆存在冲突

        将旧记忆的 confidence 降低，保留两者供后续判断。

        参数:
            old_id: 旧记忆ID
            new_id: 新记忆ID
        """
        memory = await MemoryItem.filter(id=old_id).first()
        if not memory:
            return
        memory.confidence = max(0.1, memory.confidence * 0.5)
        memory.last_access_time = datetime.now()
        await memory.save(
            update_fields=["confidence", "last_access_time"]
        )
