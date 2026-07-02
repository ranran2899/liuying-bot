"""表情包反馈学习

维护群级/用户级偏好统计、最近发送记录，
通过使用记录、反应记录与显式反馈持续优化表情包选择策略。
"""

from dataclasses import dataclass, field
import time
from typing import Any

from liuying.services.cache import CacheDict
from liuying.utils.log import logger

from ...models.sticker_feedback import StickerFeedback
from ...models.sticker_item import StickerItem
from ...models.sticker_usage import StickerUsage
from .library import StickerLibrary, sticker_library

_DEFAULT_RECENT_LIMIT = 5
"""默认最近发送记忆长度"""

_POSITIVE_REACTION_WEIGHT = 0.1
"""正向反馈权重"""

_NEGATIVE_REACTION_WEIGHT = 0.2
"""负向反馈权重"""

_REACTION_POSITIVE = "positive"
"""正向反应"""

_REACTION_NEGATIVE = "negative"
"""负向反应"""

_REACTION_NEUTRAL = "neutral"
"""中性反应"""


@dataclass(slots=True)
class StickerPreference:
    """表情包偏好

    按情绪标签记录群级/用户级的正负反馈计数。

    Attributes:
        scope_id: 范围ID（群组或用户）
        mood_stats: 按情绪分组的 {positive, negative} 计数
        last_sent_stickers: 最近发送的表情包ID列表
        last_sent_time: 最后发送时间戳
    """

    scope_id: str = ""
    mood_stats: dict[str, dict[str, int]] = field(default_factory=dict)
    last_sent_stickers: list[int] = field(default_factory=list)
    last_sent_time: float = 0.0

    def get_mood_score(self, mood: str) -> float:
        """获取某情绪的偏好评分

        参数:
            mood: 情绪标签

        返回:
            float: 偏好评分（正数偏好，负数规避，0为中立）
        """
        stats = self.mood_stats.get(mood, {})
        positive = stats.get("positive", 0)
        negative = stats.get("negative", 0)
        return (
            positive * _POSITIVE_REACTION_WEIGHT
            - negative * _NEGATIVE_REACTION_WEIGHT
        )

    def update(
        self, mood: str, is_positive: bool
    ) -> None:
        """更新偏好

        参数:
            mood: 情绪标签
            is_positive: 是否正向反馈
        """
        if mood not in self.mood_stats:
            self.mood_stats[mood] = {"positive": 0, "negative": 0}
        if is_positive:
            self.mood_stats[mood]["positive"] += 1
        else:
            self.mood_stats[mood]["negative"] += 1

    def mark_sent(self, sticker_id: int) -> None:
        """记录发送

        参数:
            sticker_id: 表情包ID
        """
        self.last_sent_stickers.append(sticker_id)
        if len(self.last_sent_stickers) > _DEFAULT_RECENT_LIMIT:
            self.last_sent_stickers.pop(0)
        self.last_sent_time = time.time()


class FeedbackLearner:
    """表情包反馈学习器

    维护群级/用户级偏好统计与最近使用记录，
    提供使用记录、反应记录、显式反馈等接口。
    """

    def __init__(
        self,
        library: StickerLibrary | None = None,
    ) -> None:
        """初始化反馈学习器

        参数:
            library: 表情包库，None时用单例
        """
        self._library = library or sticker_library
        # 偏好 24h TTL，最近使用 2h TTL
        self._group_prefs: CacheDict = CacheDict(
            "AI_STICKER_GROUP_PREFS", expire=86400, max_size=2000
        )
        self._user_prefs: CacheDict = CacheDict(
            "AI_STICKER_USER_PREFS", expire=86400, max_size=5000
        )
        self._recent_usage: CacheDict = CacheDict(
            "AI_STICKER_RECENT_USE", expire=7200, max_size=2000
        )

    def _get_pref(
        self,
        scope_id: str,
        is_group: bool,
    ) -> StickerPreference:
        """获取范围偏好（不存在时创建）

        参数:
            scope_id: 范围ID
            is_group: 是否群级偏好

        返回:
            StickerPreference: 偏好对象
        """
        store = self._group_prefs if is_group else self._user_prefs
        if scope_id not in store:
            store[scope_id] = StickerPreference(scope_id=scope_id)
        return store[scope_id]

    def get_exclude_ids(
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
        exclude: set[int] = set()
        if group_id:
            group_pref = self._get_pref(group_id, is_group=True)
            exclude.update(group_pref.last_sent_stickers)
        user_pref = self._get_pref(user_id, is_group=False)
        exclude.update(user_pref.last_sent_stickers)
        return exclude

    def get_mood_score(
        self,
        mood: str,
        group_id: str | None,
        user_id: str,
    ) -> float:
        """获取群级与用户级偏好评分总和

        参数:
            mood: 目标情绪
            group_id: 群组ID
            user_id: 用户ID

        返回:
            float: 偏好评分
        """
        score = 0.0
        if group_id:
            score += self._get_pref(
                group_id, is_group=True
            ).get_mood_score(mood)
        score += self._get_pref(
            user_id, is_group=False
        ).get_mood_score(mood)
        return score

    def mark_sent(
        self,
        group_id: str | None,
        user_id: str,
        sticker_id: int,
    ) -> None:
        """标记发送，更新偏好与最近使用

        参数:
            group_id: 群组ID
            user_id: 用户ID
            sticker_id: 表情包ID
        """
        if group_id:
            self._get_pref(
                group_id, is_group=True
            ).mark_sent(sticker_id)
        self._get_pref(user_id, is_group=False).mark_sent(sticker_id)

        if group_id:
            recent = self._recent_usage.get(group_id)
            if recent is None:
                recent = []
                self._recent_usage[group_id] = recent
            recent.append(sticker_id)
            if len(recent) > _DEFAULT_RECENT_LIMIT:
                recent.pop(0)

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
        try:
            await StickerItem.increment_usage(sticker_id)
            return await StickerUsage.add_record(
                sticker_id=sticker_id,
                user_id=user_id,
                group_id=group_id,
                bot_id=bot_id,
                context_text=context_text,
                detected_mood=detected_mood,
                persona_mood=persona_mood,
                reaction="unknown",
            )
        except Exception as e:
            logger.debug(
                f"记录表情包使用失败: {e}", command="AI", e=e
            )
            return None

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
        try:
            await StickerUsage.update_reaction(usage_id, reaction)
        except Exception as e:
            logger.debug(
                f"更新使用记录反应失败: {e}", command="AI", e=e
            )

        if not sticker_id:
            return

        is_positive = reaction == _REACTION_POSITIVE
        try:
            await StickerItem.update_feedback(sticker_id, is_positive)
        except Exception as e:
            logger.debug(
                f"更新表情包反馈计数失败: {e}", command="AI", e=e
            )

        if mood:
            if group_id:
                self._get_pref(group_id, is_group=True).update(
                    mood, is_positive
                )
            if user_id:
                self._get_pref(
                    user_id, is_group=False
                ).update(mood, is_positive)

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
        try:
            await StickerFeedback.add_feedback(
                sticker_id=sticker_id,
                user_id=user_id,
                group_id=group_id,
                feedback_type=feedback_type,
                comment=comment,
            )

            is_positive = feedback_type == "like"
            is_negative = feedback_type in ("dislike", "report")

            if is_positive or is_negative:
                await StickerItem.update_feedback(
                    sticker_id, is_positive
                )
                item = await self._library.get_item(sticker_id)
                if item:
                    for mood in item.get_mood_tags():
                        if group_id:
                            self._get_pref(
                                group_id, is_group=True
                            ).update(mood, is_positive)
                        if user_id:
                            self._get_pref(
                                user_id, is_group=False
                            ).update(mood, is_positive)

            # 举报自动禁用
            if feedback_type == "report":
                await self._library.set_disabled(sticker_id, True)
                logger.info(
                    f"表情包被举报自动禁用: {sticker_id}",
                    command="AI",
                )

            return True
        except Exception as e:
            logger.warning(
                f"记录表情包反馈失败: {e}", command="AI", e=e
            )
            return False

    def get_preference_report(
        self,
        group_id: str | None = None,
        user_id: str = "",
    ) -> dict[str, Any]:
        """获取偏好报告（不含冷却状态）

        参数:
            group_id: 群组ID
            user_id: 用户ID

        返回:
            dict: 偏好报告
        """
        report: dict[str, Any] = {}
        if group_id:
            group_pref = self._get_pref(group_id, is_group=True)
            report["group"] = {
                "scope_id": group_pref.scope_id,
                "mood_stats": dict(group_pref.mood_stats),
                "last_sent": list(group_pref.last_sent_stickers),
                "last_sent_time": group_pref.last_sent_time,
            }
        if user_id:
            user_pref = self._get_pref(user_id, is_group=False)
            report["user"] = {
                "scope_id": user_pref.scope_id,
                "mood_stats": dict(user_pref.mood_stats),
                "last_sent": list(user_pref.last_sent_stickers),
                "last_sent_time": user_pref.last_sent_time,
            }
        return report

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
        if group_id:
            self._group_prefs.pop(group_id, None)
            self._recent_usage.pop(group_id, None)
        if user_id:
            self._user_prefs.pop(user_id, None)
