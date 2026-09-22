"""记忆进化引擎

在新记忆写入后，自动判断其与同用户同人格的旧记忆的关系
（replaces/enriches/confirms/challenges），执行覆盖、合并、
巩固或冲突标记，实现记忆库的自动演化与去重。
作为组合式内部服务由 MemoryManager 构造并注入依赖。
"""

from datetime import datetime
import json
import re

from liuying.utils.log import logger

from ...models.memory_item import MemoryItem, MemoryTier
from ..llm import llm_helper
from ..llm.model_router import ROLE_INTENT, model_router
from ._common import _DEFAULT_PERSONA
from .memory_consolidate import MemoryConsolidationService
from .recall import MemoryRecallService

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


class MemoryEvolveService:
    """记忆进化服务

    提供新旧记忆关系判断及自动演化能力。
    召回与强化能力由注入的召回/巩固服务提供。
    """

    def __init__(
        self,
        recall_service: MemoryRecallService,
        consolidation_service: MemoryConsolidationService,
    ) -> None:
        """初始化进化服务

        参数:
            recall_service: 召回服务（提供候选记忆检索）
            consolidation_service: 巩固服务（提供 reinforce）
        """
        self._recall_service = recall_service
        self._consolidation_service = consolidation_service

    async def evolve_memory(
        self,
        user_id: str,
        new_memory_id: int,
        new_summary: str,
        group_id: str | None = None,
        persona_name: str = _DEFAULT_PERSONA,
    ) -> str:
        """对新记忆执行进化判断

        召回同用户同人格的相关旧记忆，优先单次批量 LLM 判断
        全部候选关系（解析失败降级回逐个判断），执行覆盖/合并/
        巩固/冲突标记。

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

            relations = await self._judge_relations_batch(
                new_summary, candidates
            )
            if relations is None:
                # 批量解析失败，降级回逐个判断
                relations = [
                    await self._judge_relation(
                        old_summary=mem["summary"],
                        new_summary=new_summary,
                    )
                    for mem in candidates
                ]

            for old_mem, relation in zip(
                candidates, relations, strict=True
            ):
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
        results = await self._recall_service.recall(
            user_id=user_id,
            query=new_summary,
            group_id=group_id,
            top_k=_MAX_CANDIDATES,
            persona_name=persona_name,
        )
        candidates: list[dict] = []
        for r in results:
            if r.get("id") == new_memory_id:
                continue
            if r.get("tier") == MemoryTier.BACKGROUND:
                continue
            candidates.append(r)
        return candidates

    async def _judge_relations_batch(
        self,
        new_summary: str,
        candidates: list[dict],
    ) -> list[str] | None:
        """单次 LLM 批量判断新旧记忆关系

        将全部候选摘要（带索引）拼入一个 prompt，要求 LLM 输出
        JSON 数组 [{"index": 0, "relation": "replaces",
        "reason": "..."}]，把原先最多 5 次串行 LLM 调用压缩为 1 次。

        参数:
            new_summary: 新记忆摘要
            candidates: 候选旧记忆列表

        返回:
            list[str] | None: 每个候选的关系类型列表；
            LLM 失败或解析失败返回 None（调用方降级为逐个判断）
        """
        lines = [
            f"{idx}. {mem['summary']}"
            for idx, mem in enumerate(candidates)
        ]
        prompt = (
            "你是一个记忆关系判断助手。\n"
            "请判断新记忆与下列每条旧记忆之间的关系，"
            "输出JSON数组（只输出JSON，不要其他内容）：\n"
            '[{"index": 0, "relation": "replaces", "reason": "简要原因"}]\n\n'
            "relation 只能是以下五个英文单词之一：\n"
            "- replaces: 新记忆完全覆盖旧记忆（旧信息已过时或被纠正）\n"
            "- enriches: 新记忆补充旧记忆（两者可合并为更完整记录）\n"
            "- confirms: 新记忆确认旧记忆（内容基本一致，巩固旧记忆）\n"
            "- challenges: 新记忆与旧记忆矛盾（保留两者，标记冲突）\n"
            "- unrelated: 两者无直接关系\n\n"
            "旧记忆列表：\n"
            + "\n".join(lines)
            + "\n\n新记忆：\n"
            + new_summary
            + "\n\n要求：数组必须覆盖全部旧记忆，"
            "每项的 index 对应旧记忆列表的序号。"
        )
        try:
            role = model_router.resolve(ROLE_INTENT)
            _, content = await llm_helper.chat(
                [{"role": "user", "content": prompt}],
                model=role.model or None,
                options=role.apply_to_options({"temperature": 0.0}),
                provider_name=role.provider or None,
            )
        except Exception as e:
            logger.debug(
                f"批量关系判断失败: {e}", command="AI", e=e
            )
            return None
        return self._parse_relations(content, len(candidates))

    @staticmethod
    def _parse_relations(raw: str, count: int) -> list[str] | None:
        """解析批量关系判断的 LLM JSON 输出

        严格校验：数组必须恰好覆盖全部候选索引、relation
        必须为有效值，任一不满足即返回 None 触发降级，
        宁可降级也不应用不可信的批量结果。

        参数:
            raw: LLM 返回的原始文本
            count: 候选数量

        返回:
            list[str] | None: 关系类型列表，解析失败返回 None
        """
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(
                r"^```(?:json)?\s*", "", text
            ).rstrip("`").strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, list):
            return None
        relations = [_RELATION_UNRELATED] * count
        seen: set[int] = set()
        for item in data:
            if not isinstance(item, dict):
                return None
            idx = item.get("index", -1)
            if not isinstance(idx, int) or not 0 <= idx < count:
                return None
            if idx in seen:
                return None
            relation = str(item.get("relation", "")).strip().lower()
            if relation not in _VALID_RELATIONS:
                return None
            relations[idx] = relation
            seen.add(idx)
        if len(seen) != count:
            return None
        return relations

    async def _judge_relation(
        self,
        old_summary: str,
        new_summary: str,
    ) -> str:
        """使用 LLM 判断新旧记忆关系（单个）

        作为批量判断解析失败时的降级路径保留。

        参数:
            old_summary: 旧记忆摘要
            new_summary: 新记忆摘要

        返回:
            str: 关系类型
        """
        prompt = (
            "你是一个记忆关系判断助手。\n"
            "请判断新记忆与旧记忆之间的关系，只输出以下五个英文单词之一：\n\n"
            "- replaces: 新记忆完全覆盖旧记忆（旧信息已过时或被纠正）\n"
            "- enriches: 新记忆补充旧记忆（两者可合并为更完整记录）\n"
            "- confirms: 新记忆确认旧记忆（内容基本一致，巩固旧记忆）\n"
            "- challenges: 新记忆与旧记忆矛盾（保留两者，标记冲突）\n"
            "- unrelated: 两者无直接关系\n\n"
            "旧记忆：\n"
            f"{old_summary}\n\n"
            "新记忆：\n"
            f"{new_summary}\n\n"
            "只输出一个英文单词，不要任何其他内容。"
        )
        try:
            role = model_router.resolve(ROLE_INTENT)
            _, content = await llm_helper.chat(
                [{"role": "user", "content": prompt}],
                model=role.model or None,
                options=role.apply_to_options({"temperature": 0.0}),
                provider_name=role.provider or None,
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
            await self._consolidation_service.reinforce(old_id)
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
        memory.tier = MemoryTier.BACKGROUND
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
        prompt = (
            "请合并以下两条记忆为一条更完整的摘要，保留双方关键信息。\n\n"
            f"旧记忆：{old_summary}\n"
            f"新记忆：{new_summary}\n\n"
            "要求：\n"
            "1. 只输出合并后的摘要文本\n"
            "2. 不超过100字\n"
            "3. 不输出任何解释"
        )
        try:
            role = model_router.resolve(ROLE_INTENT)
            merged = await llm_helper.chat_text(
                [{"role": "user", "content": prompt}],
                model=role.model or None,
                options=role.apply_to_options({"temperature": 0.3}),
                provider_name=role.provider or None,
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
