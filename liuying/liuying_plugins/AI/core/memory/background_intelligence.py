"""后台智能模块

监听新记忆写入后触发后台处理（去重/巩固/晶体化）。
通过防抖调度避免短时间大量 LLM 调用，
配合每小时/每日配额控制成本。
"""

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from liuying.utils.log import logger

from ...models.memory_item import MemoryItem
from ._common import _DEFAULT_PERSONA

_DEBOUNCE_SECONDS = 30.0
"""防抖等待秒数（收集窗口）"""

_HOURLY_QUOTA = 20
"""每小时 LLM 任务配额"""

_DAILY_QUOTA = 200
"""每日 LLM 任务配额"""

_CRYSTALIZE_THRESHOLD = 3
"""晶体化晋升阈值（访问次数）"""

_DEDUP_SIMILARITY = 0.85
"""去重相似度阈值"""

_BATCH_SIZE = 10
"""单批处理记忆数量"""


class BackgroundIntelligence:
    """后台智能管理器

    监听新记忆写入，防抖触发去重/巩固/晶体化任务。
    通过配额控制避免 LLM 调用过载。
    """

    def __init__(self) -> None:
        """初始化后台智能管理器"""
        self._lock = asyncio.Lock()
        self._pending: dict[str, list[dict[str, Any]]] = defaultdict(list)
        """待处理记忆队列（key=user_id|persona_name）"""
        self._task: asyncio.Task | None = None
        """防抖定时任务"""
        self._hourly_count: int = 0
        self._daily_count: int = 0
        self._hour_start: datetime = datetime.now()
        self._day_start: datetime = datetime.now()

    async def notify_memory_added(
        self,
        user_id: str,
        memory_id: int,
        summary: str,
        group_id: str | None = None,
        persona_name: str = _DEFAULT_PERSONA,
    ) -> None:
        """通知新记忆写入（触发防抖调度）

        参数:
            user_id: 用户ID
            memory_id: 记忆ID
            summary: 记忆摘要
            group_id: 群组ID
            persona_name: bot人格名
        """
        key = f"{user_id}|{persona_name}"
        async with self._lock:
            self._pending[key].append(
                {
                    "user_id": user_id,
                    "memory_id": memory_id,
                    "summary": summary,
                    "group_id": group_id,
                    "persona_name": persona_name,
                    "timestamp": datetime.now(),
                }
            )
            if self._task is None or self._task.done():
                self._task = asyncio.create_task(
                    self._debounced_process()
                )

    async def _debounced_process(self) -> None:
        """防抖处理：等待窗口结束后批量处理待处理记忆"""
        await asyncio.sleep(_DEBOUNCE_SECONDS)
        async with self._lock:
            batches = dict(self._pending)
            self._pending.clear()
            self._task = None
        if not batches:
            return
        for key, memories in batches.items():
            if not memories:
                continue
            await self._process_batch(key, memories)

    async def _process_batch(
        self, key: str, memories: list[dict[str, Any]]
    ) -> None:
        """处理一批待处理记忆

        参数:
            key: 用户+人格键
            memories: 待处理记忆列表
        """
        if not self._check_quota():
            logger.debug(
                f"后台智能配额已满，跳过批次: {key}",
                command="AI",
            )
            return
        first = memories[0]
        user_id = first["user_id"]
        persona_name = first["persona_name"]
        group_id = first.get("group_id")
        try:
            dedup_count = await self._deduplicate(
                user_id=user_id,
                persona_name=persona_name,
                group_id=group_id,
            )
            crystal_count = await self._crystallize(
                user_id=user_id,
                persona_name=persona_name,
            )
            self._increment_quota(dedup_count + crystal_count)
            if dedup_count + crystal_count > 0:
                logger.info(
                    f"后台智能处理: user={user_id} "
                    f"dedup={dedup_count} crystal={crystal_count}",
                    command="AI",
                )
        except Exception as e:
            logger.warning(
                f"后台智能处理失败: {key} -> {e}",
                command="AI",
                e=e,
            )

    async def _deduplicate(
        self,
        user_id: str,
        persona_name: str,
        group_id: str | None = None,
    ) -> int:
        """检测并合并相似记忆

        参数:
            user_id: 用户ID
            persona_name: bot人格名
            group_id: 群组ID

        返回:
            int: 合并的记忆数量
        """
        query = MemoryItem.filter(
            user_id=user_id,
            persona_name=persona_name,
            tier__in=["working", "episodic"],
        )
        if group_id:
            query = query.filter(group_id=group_id)
        memories = await query.order_by("-create_time").limit(
            _BATCH_SIZE * 2
        ).all()
        if len(memories) < 2:
            return 0
        merged_count = 0
        seen: list[MemoryItem] = []
        for mem in memories:
            is_dup = False
            for seen_mem in seen:
                similarity = self._text_similarity(
                    mem.summary, seen_mem.summary
                )
                if similarity >= _DEDUP_SIMILARITY:
                    seen_mem.reinforcement_count += 1
                    await seen_mem.save(
                        update_fields=["reinforcement_count"]
                    )
                    mem.superseded_by = seen_mem.id
                    mem.tier = "background"
                    await mem.save(
                        update_fields=["superseded_by", "tier"]
                    )
                    merged_count += 1
                    is_dup = True
                    break
            if not is_dup:
                seen.append(mem)
        return merged_count

    async def _crystallize(
        self,
        user_id: str,
        persona_name: str,
    ) -> int:
        """晶体化高频访问的情景记忆为语义记忆

        参数:
            user_id: 用户ID
            persona_name: bot人格名

        返回:
            int: 晶体化的记忆数量
        """
        memories = await MemoryItem.filter(
            user_id=user_id,
            persona_name=persona_name,
            tier="episodic",
            access_count__gte=_CRYSTALIZE_THRESHOLD,
            is_protected=False,
        ).limit(_BATCH_SIZE).all()
        count = 0
        for mem in memories:
            mem.tier = "semantic"
            mem.is_protected = True
            await mem.save(
                update_fields=["tier", "is_protected"]
            )
            count += 1
        return count

    @staticmethod
    def _text_similarity(text_a: str, text_b: str) -> float:
        """计算两段文本的 Jaccard 相似度

        参数:
            text_a: 文本A
            text_b: 文本B

        返回:
            float: 相似度（0-1）
        """
        if not text_a or not text_b:
            return 0.0
        set_a = set(text_a.split())
        set_b = set(text_b.split())
        if not set_a or not set_b:
            return 0.0
        intersection = set_a & set_b
        union = set_a | set_b
        return len(intersection) / len(union)

    def _check_quota(self) -> bool:
        """检查 LLM 调用配额是否充足

        返回:
            bool: 是否可用
        """
        now = datetime.now()
        if now - self._hour_start >= timedelta(hours=1):
            self._hour_start = now
            self._hourly_count = 0
        if now - self._day_start >= timedelta(days=1):
            self._day_start = now
            self._daily_count = 0
        return (
            self._hourly_count < _HOURLY_QUOTA
            and self._daily_count < _DAILY_QUOTA
        )

    def _increment_quota(self, count: int) -> None:
        """增加配额计数

        参数:
            count: 增加的数量
        """
        self._hourly_count += count
        self._daily_count += count


background_intelligence = BackgroundIntelligence()
"""后台智能管理器单例"""
