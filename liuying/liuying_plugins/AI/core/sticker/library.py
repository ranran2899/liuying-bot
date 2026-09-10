"""表情包库管理

提供多维度检索（按情绪/语义/文本/随机）、库统计与禁用管理。
导入与扫描逻辑由 sticker.importer 提供。
"""

from collections import defaultdict
from dataclasses import dataclass, field
import json
from pathlib import Path
import random

from ...models.sticker_item import StickerItem

_DEFAULT_STICKER_ROOT = Path("data") / "ai_plugin" / "stickers"
"""默认表情包根目录"""


@dataclass(slots=True)
class LibraryStats:
    """库统计

    Attributes:
        total: 总数
        active: 活动数
        disabled: 禁用数
        by_mood: 按情绪分组计数
        by_source: 按来源分组计数
        total_usage: 总使用次数
    """

    total: int = 0
    active: int = 0
    disabled: int = 0
    by_mood: dict[str, int] = field(default_factory=dict)
    by_source: dict[str, int] = field(default_factory=dict)
    total_usage: int = 0

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "total": self.total,
            "active": self.active,
            "disabled": self.disabled,
            "by_mood": dict(self.by_mood),
            "by_source": dict(self.by_source),
            "total_usage": self.total_usage,
        }


class StickerLibrary:
    """表情包库管理器

    提供多维度检索与统计能力。导入与扫描委托给 StickerImporter。
    """

    def __init__(
        self,
        root_dir: Path | None = None,
        llm_helper=None,
    ) -> None:
        """初始化表情包库

        参数:
            root_dir: 表情包根目录，None时用默认
            llm_helper: 已废弃，仅为兼容旧API保留
        """
        self.root_dir = root_dir or _DEFAULT_STICKER_ROOT

    async def search_by_mood(
        self,
        mood: str,
        limit: int = 20,
        exclude_ids: set[int] | None = None,
    ) -> list[StickerItem]:
        """按情绪检索

        参数:
            mood: 情绪标签
            limit: 返回上限
            exclude_ids: 需排除的表情包ID集合

        返回:
            list[StickerItem]: 匹配的表情包列表
        """
        items = await StickerItem.list_active(
            mood=mood, limit=limit * 2
        )
        exclude = exclude_ids or set()
        return [it for it in items if it.id not in exclude][:limit]

    async def search_by_text(
        self,
        query: str,
        limit: int = 20,
    ) -> list[StickerItem]:
        """按文本检索

        参数:
            query: 查询文本（匹配名称/描述/语义标签）
            limit: 返回上限

        返回:
            list[StickerItem]: 匹配的表情包列表
        """
        if not query:
            return []
        results = await StickerItem.search(query, limit=limit)
        return results

    async def search_by_semantic(
        self,
        semantic: str,
        limit: int = 20,
    ) -> list[StickerItem]:
        """按语义标签检索

        参数:
            semantic: 语义标签
            limit: 返回上限

        返回:
            list[StickerItem]: 匹配的表情包列表
        """
        items = await StickerItem.list_active(limit=limit * 3)
        return [
            it for it in items
            if semantic in it.get_semantic_tags()
        ][:limit]

    async def get_random_by_mood(
        self,
        mood: str,
        exclude_ids: set[int] | None = None,
        limit: int = 1,
    ) -> list[StickerItem]:
        """按情绪随机获取

        参数:
            mood: 情绪标签
            exclude_ids: 需排除的表情包ID集合
            limit: 返回数量

        返回:
            list[StickerItem]: 随机表情包列表
        """
        items = await self.search_by_mood(
            mood, limit=50, exclude_ids=exclude_ids
        )
        if not items:
            return []
        # 按评分加权随机
        weights = [max(it.score, 0.01) for it in items]
        total = sum(weights)
        if total <= 0:
            return random.sample(
                items, min(limit, len(items))
            )

        chosen: list[StickerItem] = []
        pool = list(items)
        pool_weights = list(weights)
        for _ in range(min(limit, len(pool))):
            if not pool:
                break
            idx = random.choices(
                range(len(pool)),
                weights=pool_weights,
                k=1,
            )[0]
            chosen.append(pool.pop(idx))
            pool_weights.pop(idx)
        return chosen

    async def get_fallback_sticker(
        self,
        exclude_ids: set[int] | None = None,
    ) -> StickerItem | None:
        """获取兜底表情包（无情绪过滤）

        参数:
            exclude_ids: 需排除的表情包ID集合

        返回:
            StickerItem | None: 兜底表情包
        """
        items = await StickerItem.list_active(limit=20)
        exclude = exclude_ids or set()
        candidates = [it for it in items if it.id not in exclude]
        if not candidates:
            return None
        return random.choice(candidates)

    async def get_item(
        self, item_id: int
    ) -> StickerItem | None:
        """获取单个表情包

        参数:
            item_id: 表情包ID

        返回:
            StickerItem | None: 表情包条目
        """
        return await StickerItem.filter(id=item_id).first()

    async def get_item_by_path(
        self, file_path: str
    ) -> StickerItem | None:
        """按路径获取表情包

        参数:
            file_path: 相对路径

        返回:
            StickerItem | None: 表情包条目
        """
        return await StickerItem.filter(
            file_path=file_path
        ).first()

    async def get_stats(self) -> LibraryStats:
        """获取库统计（SQL聚合，避免加载ORM对象）

        total/active/total_usage/by_source 均走数据库聚合；
        by_mood 因 mood_tags 为JSON数组文本列无法纯SQL分组，
        仅拉取该轻量列后在Python侧解析计数。

        返回:
            LibraryStats: 统计结果
        """
        total = await StickerItem.filter().count()
        active = await StickerItem.filter(
            is_disabled=False
        ).count()
        total_usage = int(
            await StickerItem.filter().sum("usage_count") or 0
        )
        by_source = dict(
            await StickerItem.filter().group_count("source")
        )
        stats = LibraryStats(
            total=total,
            active=active,
            disabled=total - active,
            total_usage=total_usage,
            by_source=by_source,
        )

        by_mood: defaultdict[str, int] = defaultdict(int)
        mood_columns = await StickerItem.filter().values_list(
            "mood_tags", flat=True
        )
        for raw_tags in mood_columns:
            try:
                tags = json.loads(raw_tags or "[]")
            except (json.JSONDecodeError, TypeError):
                continue
            for tag in tags:
                if tag:
                    by_mood[str(tag)] += 1
        stats.by_mood = dict(by_mood)
        return stats

    async def set_disabled(
        self, item_id: int, disabled: bool
    ) -> bool:
        """禁用/启用表情包

        参数:
            item_id: 表情包ID
            disabled: 是否禁用

        返回:
            bool: 是否成功
        """
        await StickerItem.set_disabled(item_id, disabled)
        return True


sticker_library = StickerLibrary()
"""表情包库管理器单例"""
