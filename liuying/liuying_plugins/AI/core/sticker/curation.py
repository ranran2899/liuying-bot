"""表情包策展

基于情绪检测、用户反馈、群级/用户级偏好与冷却管理，
智能选择回复表情包。反馈学习逻辑由 FeedbackLearner 承担。
"""

import random
import time
from typing import Any

from liuying.services.cache import CacheDict

from ...config import get_config
from ...models.sticker_item import StickerItem
from ...models.sticker_usage import StickerUsage
from .feedback import FeedbackLearner
from .library import StickerLibrary, sticker_library

_DEFAULT_COOLDOWN_SECONDS = 180
"""默认冷却时间（秒）"""

_MOOD_KEYWORDS: dict[str, list[str]] = {
    "happy": ["开心", "高兴", "快乐", "哈哈", "嘻嘻", "^_^", "好耶"],
    "sad": ["难过", "伤心", "哭", "呜呜", "失落"],
    "excited": ["激动", "兴奋", "太棒了", "好棒"],
    "angry": ["生气", "愤怒", "哼", "可恶"],
    "shy": ["害羞", "脸红", "不好意思"],
    "calm": ["嗯", "好的", "了解", "知道", "哦"],
    "warm": ["谢谢", "感谢", "辛苦", "温暖"],
    "playful": ["嘿嘿", "哈哈", "逗", "玩笑"],
}
"""情绪关键词映射"""


class StickerCuration:
    """表情包策展器

    综合情绪检测、库检索、偏好学习、冷却管理，
    智能选择回复表情包；偏好与反馈学习委托给
    FeedbackLearner。
    """

    def __init__(
        self,
        library: StickerLibrary | None = None,
    ) -> None:
        """初始化策展器

        参数:
            library: 表情包库，None时用单例
        """
        self._library = library or sticker_library
        self._feedback_learner = FeedbackLearner(library=library)
        # 群冷却 2h TTL
        self._group_cooldowns: CacheDict = CacheDict(
            "AI_STICKER_GROUP_CD", expire=7200, max_size=2000
        )

    def _get_library(self) -> StickerLibrary:
        """获取表情包库

        返回:
            StickerLibrary: 表情包库实例
        """
        return self._library

    def _detect_mood(
        self, text: str, persona_mood: str, hint: str = ""
    ) -> str:
        """从文本和人格情绪检测实际情绪

        参数:
            text: 回复文本
            persona_mood: 人格默认情绪倾向
            hint: 表情包情绪提示

        返回:
            str: 检测到的情绪名
        """
        if hint:
            hint_lower = hint.lower()
            for mood in _MOOD_KEYWORDS:
                if mood in hint_lower:
                    return mood

        text_lower = text.lower()
        for mood, keywords in _MOOD_KEYWORDS.items():
            for kw in keywords:
                if kw in text or kw.lower() in text_lower:
                    return mood
        return persona_mood or "neutral"

    def _in_cooldown(self, group_id: str | None) -> bool:
        """检查是否在冷却期

        参数:
            group_id: 群组ID，None为私聊（无冷却）

        返回:
            bool: 是否在冷却期
        """
        if not group_id:
            return False
        last = self._group_cooldowns.get(group_id, 0.0)
        return (time.time() - last) < _DEFAULT_COOLDOWN_SECONDS

    def _mark_sent(
        self,
        group_id: str | None,
        user_id: str,
        sticker_id: int,
    ) -> None:
        """标记发送（更新冷却与偏好）

        参数:
            group_id: 群组ID
            user_id: 用户ID
            sticker_id: 表情包ID
        """
        now = time.time()
        if group_id:
            self._group_cooldowns[group_id] = now
        self._feedback_learner.mark_sent(
            group_id, user_id, sticker_id
        )

    def _get_exclude_ids(
        self,
        group_id: str | None,
        user_id: str,
    ) -> set[int]:
        """获取需排除的表情包ID集合

        参数:
            group_id: 群组ID
            user_id: 用户ID

        返回:
            set[int]: 排除集合
        """
        return self._feedback_learner.get_exclude_ids(
            group_id, user_id
        )

    def _score_item(
        self,
        item: StickerItem,
        mood: str,
        group_id: str | None,
        user_id: str,
    ) -> float:
        """对单个表情包评分

        参数:
            item: 表情包条目
            mood: 目标情绪
            group_id: 群组ID
            user_id: 用户ID

        返回:
            float: 评分
        """
        base_score = item.score
        if mood in item.get_mood_tags():
            base_score += 1.0
        base_score += self._feedback_learner.get_mood_score(
            mood, group_id, user_id
        )
        return max(0.01, base_score)

    def should_send(
        self,
        group_id: str | None,
        is_private: bool,
        probability: float | None = None,
    ) -> bool:
        """决策是否发送表情包

        参数:
            group_id: 群组ID
            is_private: 是否私聊
            probability: 触发概率，None时用配置默认

        返回:
            bool: 是否发送
        """
        if not get_config("STICKER_ENABLED", True):
            return False
        if not is_private and self._in_cooldown(group_id):
            return False
        prob = (
            probability if probability is not None
            else float(get_config("STICKER_PROBABILITY", 0.24))
        )
        return random.random() < prob

    async def choose_for_reply(
        self,
        text: str,
        persona_mood: str = "neutral",
        mood_hint: str = "",
        group_id: str | None = None,
        user_id: str = "",
        is_private: bool = False,
        force: bool = False,
    ) -> StickerItem | None:
        """为回复选择表情包

        参数:
            text: 回复文本
            persona_mood: 人格情绪倾向
            mood_hint: 表情包情绪提示
            group_id: 群组ID
            user_id: 用户ID
            is_private: 是否私聊
            force: 是否强制发送（忽略概率检查）

        返回:
            StickerItem | None: 选中的表情包，不发时返回None
        """
        if not force and not self.should_send(group_id, is_private):
            return None

        library = self._get_library()
        mood = self._detect_mood(text, persona_mood, mood_hint)
        exclude_ids = self._get_exclude_ids(group_id, user_id)

        candidates = await library.search_by_mood(
            mood=mood, limit=20, exclude_ids=exclude_ids
        )

        if not candidates:
            candidates = await library.search_by_mood(
                mood=persona_mood or "neutral",
                limit=10,
                exclude_ids=exclude_ids,
            )

        if not candidates:
            candidates = await library.get_random_by_mood(
                mood="happy", exclude_ids=exclude_ids, limit=5
            )

        if not candidates:
            fallback = await library.get_fallback_sticker(
                exclude_ids=exclude_ids
            )
            return fallback

        # 评分加权随机
        scored = [
            (item, self._score_item(item, mood, group_id, user_id))
            for item in candidates
        ]
        total_score = sum(s for _, s in scored)
        if total_score <= 0:
            return random.choice(candidates)

        weights = [s / total_score for _, s in scored]
        chosen_idx = random.choices(
            range(len(scored)),
            weights=weights,
            k=1,
        )[0]
        chosen = scored[chosen_idx][0]

        self._mark_sent(group_id, user_id, chosen.id)
        return chosen

    async def record_usage(
        self,
        sticker_id: int,
        context_text: str = "",
        detected_mood: str = "",
        persona_mood: str = "",
        group_id: str = "",
        user_id: str = "",
        bot_id: str = "",
    ) -> StickerUsage | None:
        """记录表情包使用

        参数:
            sticker_id: 表情包ID
            context_text: 触发文本
            detected_mood: 检测到的情绪
            persona_mood: 人格情绪
            group_id: 群组ID
            user_id: 用户ID
            bot_id: 机器人ID

        返回:
            StickerUsage | None: 使用记录
        """
        return await self._feedback_learner.record_usage(
            sticker_id=sticker_id,
            context_text=context_text,
            detected_mood=detected_mood,
            persona_mood=persona_mood,
            group_id=group_id,
            user_id=user_id,
            bot_id=bot_id,
        )

    async def record_reaction(
        self,
        usage_id: int,
        reaction: str,
        sticker_id: int = 0,
        mood: str = "",
        group_id: str = "",
        user_id: str = "",
    ) -> None:
        """记录用户反应并更新反馈

        参数:
            usage_id: 使用记录ID
            reaction: 反应类型（positive/negative/neutral）
            sticker_id: 表情包ID（用于更新计数）
            mood: 表情包情绪
            group_id: 群组ID
            user_id: 用户ID
        """
        await self._feedback_learner.record_reaction(
            usage_id=usage_id,
            reaction=reaction,
            sticker_id=sticker_id,
            mood=mood,
            group_id=group_id,
            user_id=user_id,
        )

    async def record_feedback(
        self,
        sticker_id: int,
        user_id: str = "",
        group_id: str = "",
        feedback_type: str = "like",
        comment: str = "",
    ) -> bool:
        """记录显式反馈

        参数:
            sticker_id: 表情包ID
            user_id: 用户ID
            group_id: 群组ID
            feedback_type: 反馈类型（like/dislike/report/comment）
            comment: 评论内容

        返回:
            bool: 是否成功
        """
        return await self._feedback_learner.record_feedback(
            sticker_id=sticker_id,
            user_id=user_id,
            group_id=group_id,
            feedback_type=feedback_type,
            comment=comment,
        )

    def get_preference_report(
        self,
        group_id: str | None = None,
        user_id: str = "",
    ) -> dict[str, Any]:
        """获取偏好报告

        参数:
            group_id: 群组ID
            user_id: 用户ID

        返回:
            dict: 偏好报告
        """
        report = self._feedback_learner.get_preference_report(
            group_id, user_id
        )
        if group_id and "group" in report:
            report["group"]["in_cooldown"] = self._in_cooldown(
                group_id
            )
        return report

    def reset_cooldown(self, group_id: str) -> None:
        """重置群冷却

        参数:
            group_id: 群组ID
        """
        self._group_cooldowns.pop(group_id, None)

    def reset_preference(
        self,
        group_id: str | None = None,
        user_id: str = "",
    ) -> None:
        """重置偏好

        参数:
            group_id: 群组ID
            user_id: 用户ID
        """
        self._feedback_learner.reset_preference(
            group_id=group_id, user_id=user_id
        )
        if group_id:
            self._group_cooldowns.pop(group_id, None)


sticker_curation = StickerCuration()
"""表情包策展器单例"""
