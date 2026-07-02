"""记忆进化引擎

分析新旧记忆之间的关系（替换/补充/确认/质疑），
自动更新记忆内容，保持记忆系统的一致性与准确性。
"""

import json
import re

from liuying.utils.log import logger

from ...models.memory_item import MemoryItem
from ..llm import llm_helper
from .manager import memory_manager

_RELATION_PROMPT = """请分析新旧两条记忆之间的关系。

旧记忆：{old}
新信息：{new}

关系类型（只返回一个词）：
- replace: 新信息替换旧记忆（旧记忆过时）
- supplement: 新信息补充旧记忆（扩展细节）
- confirm: 新信息确认旧记忆（重复或一致）
- contradict: 新信息与旧记忆矛盾
- unrelated: 无关

只返回JSON：{{"relation": "replace", "reason": "简短原因"}}"""

_RELATIONS = frozenset({
    "replace", "supplement", "confirm", "contradict", "unrelated",
})
"""有效关系类型"""

_MAX_MEMORY_LEN = 300
"""单条记忆最大长度"""

_MAX_COMPARE_PER_RUN = 20
"""单次进化最大比较数量"""


class MemoryEvolver:
    """记忆进化引擎

    当新记忆写入时，检索相关旧记忆，通过LLM判断关系：
    - replace: 标记旧记忆为过时，用新记忆替代
    - supplement: 将新信息合并到旧记忆
    - confirm: 增加旧记忆的巩固计数
    - contradict: 保留两条，标记矛盾关系
    - unrelated: 无操作
    """

    def __init__(self, llm=None) -> None:
        """初始化

        参数:
            llm: LLM助手实例
        """
        self._llm = llm

    def _get_llm(self):
        """延迟获取LLM助手"""
        if self._llm is None:
            self._llm = llm_helper
        return self._llm

    async def evolve(
        self,
        new_memory_id: int,
        user_id: str,
        group_id: str | None = None,
    ) -> int:
        """对新记忆执行进化分析

        参数:
            new_memory_id: 新写入的记忆ID
            user_id: 用户ID
            group_id: 群组ID

        返回:
            int: 处理的关系数量
        """
        new_memory = await MemoryItem.filter(id=new_memory_id).first()
        if not new_memory:
            return 0

        try:
            old_memories = await memory_manager.recall(
                user_id=user_id,
                query=new_memory.summary,
                group_id=group_id,
                top_k=5,
                persona_name=(
                    new_memory.persona_name or "default"
                ),
            )
        except Exception as e:
            logger.debug(
                f"记忆进化: 召回相关记忆失败: {e}",
                command="AI",
                e=e,
            )
            return 0

        old_memories = [
            m for m in old_memories if m["id"] != new_memory_id
        ]
        if not old_memories:
            return 0

        count = 0
        for old in old_memories[:_MAX_COMPARE_PER_RUN]:
            try:
                relation = await self._analyze_relation(
                    old["summary"], new_memory.summary
                )
                if relation and relation.get("relation") != "unrelated":
                    await self._apply_relation(
                        old_memory_id=old["id"],
                        new_memory_id=new_memory_id,
                        relation=relation["relation"],
                        new_summary=new_memory.summary,
                    )
                    count += 1
            except Exception as e:
                logger.debug(
                    f"记忆进化: 关系处理失败: {e}",
                    command="AI",
                    e=e,
                )
        if count > 0:
            logger.info(
                f"记忆进化: 处理{count}条关系",
                command="AI",
            )
        return count

    async def _analyze_relation(
        self,
        old_text: str,
        new_text: str,
    ) -> dict | None:
        """分析新旧记忆关系

        参数:
            old_text: 旧记忆文本
            new_text: 新记忆文本

        返回:
            dict | None: {relation, reason}
        """
        prompt = _RELATION_PROMPT.format(
            old=old_text[:_MAX_MEMORY_LEN],
            new=new_text[:_MAX_MEMORY_LEN],
        )
        try:
            _, raw = await self._get_llm().chat(
                [{"role": "user", "content": prompt}],
                options={"temperature": 0.1},
            )
            return self._parse_relation_json(raw)
        except Exception as e:
            logger.debug(
                f"记忆进化: 关系分析失败: {e}",
                command="AI",
                e=e,
            )
            return None

    def _parse_relation_json(self, raw: str) -> dict | None:
        """解析关系JSON

        参数:
            raw: LLM返回文本

        返回:
            dict | None: {relation, reason}
        """
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            result = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            match = re.search(r"\{[^{}]+\}", text)
            if not match:
                return None
            try:
                result = json.loads(match.group())
            except (json.JSONDecodeError, ValueError):
                return None

        relation = result.get("relation", "unrelated")
        if relation not in _RELATIONS:
            return None
        return result

    async def _apply_relation(
        self,
        old_memory_id: int,
        new_memory_id: int,
        relation: str,
        new_summary: str,
    ) -> None:
        """应用记忆关系

        参数:
            old_memory_id: 旧记忆ID
            new_memory_id: 新记忆ID
            relation: 关系类型
            new_summary: 新记忆摘要
        """
        old = await MemoryItem.filter(id=old_memory_id).first()
        if not old:
            return

        if relation == "replace":
            old.is_protected = False
            old.tier = "background"
            await old.save(
                update_fields=["is_protected", "tier"]
            )
        elif relation == "supplement":
            combined = f"{old.summary} {new_summary}"
            old.summary = combined[:_MAX_MEMORY_LEN]
            await old.save(update_fields=["summary"])
        elif relation == "confirm":
            await memory_manager.reinforce(old_memory_id)
        elif relation == "contradict":
            old.is_protected = True
            await old.save(update_fields=["is_protected"])


memory_evolver = MemoryEvolver()
"""记忆进化器单例"""
