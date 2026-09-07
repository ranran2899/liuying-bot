"""群禁言感知

被动监听 group_ban notice 事件更新Bot禁言状态，
基于本地缓存判断当前是否处于禁言期。
"""

import time
from typing import Any, ClassVar

from liuying.services.cache import CacheDict
from liuying.utils.log import logger

__all__ = ["GroupMuteTracker", "group_mute_tracker"]


class GroupMuteTracker:
    """群禁言状态追踪器

    封装群禁言状态的设置、查询与notice更新能力，
    通过类变量共享禁言状态缓存，所有方法均为静态方法。
    """

    _mute_state_cache: ClassVar[CacheDict] = CacheDict(
        "AI_GROUP_MUTE_STATE", expire=600, max_size=1000
    )
    """group_id -> {muted_until: ts, checked_at: ts} 禁言状态缓存（10分钟TTL）"""

    @staticmethod
    def _now() -> float:
        """获取当前时间戳

        返回:
            float: 当前时间戳
        """
        return time.time()

    @staticmethod
    def set_group_mute_until(
        group_id: str,
        muted_until: float,
        *,
        source: str = "",
    ) -> None:
        """设置群禁言截止时间

        参数:
            group_id: 群组ID
            muted_until: 禁言截止时间戳（0表示已解除）
            source: 来源标记（notice/member_info）
        """
        if not group_id:
            return
        gid = str(group_id)
        GroupMuteTracker._mute_state_cache.set(
            gid,
            {
                "muted_until": float(muted_until),
                "checked_at": GroupMuteTracker._now(),
            },
        )
        logger.debug(
            f"群 {group_id} 禁言状态更新: until={muted_until} source={source}",
            command="AI",
            group_id=group_id,
        )

    @staticmethod
    def get_group_mute_until(group_id: str) -> float:
        """获取群禁言截止时间

        参数:
            group_id: 群组ID

        返回:
            float: 禁言截止时间戳，0表示未禁言或无记录
        """
        cached = GroupMuteTracker._mute_state_cache.get(
            str(group_id)
        )
        if not cached:
            return 0.0
        return float(cached.get("muted_until", 0.0) or 0.0)

    @staticmethod
    def is_group_muted(
        group_id: str,
        *,
        now_ts: float | None = None,
    ) -> bool:
        """判断群是否处于禁言期

        参数:
            group_id: 群组ID
            now_ts: 当前时间戳，None时用time.time()

        返回:
            bool: 是否处于禁言期
        """
        now_value = (
            GroupMuteTracker._now()
            if now_ts is None
            else float(now_ts)
        )
        muted_until = GroupMuteTracker.get_group_mute_until(
            group_id
        )
        if muted_until <= 0:
            return False
        return muted_until > now_value

    @staticmethod
    def update_group_mute_from_notice(
        event: Any,
        *,
        bot_self_id: str = "",
    ) -> bool:
        """从 notice 事件更新禁言状态

        仅处理 ban 自己的 group_ban 事件。

        参数:
            event: notice事件对象
            bot_self_id: Bot自身ID

        返回:
            bool: 是否更新了状态
        """
        notice_type = str(
            getattr(event, "notice_type", "") or ""
        ).strip()
        if notice_type != "group_ban":
            return False

        target_user_id = str(
            getattr(event, "user_id", "") or ""
        ).strip()
        self_id = str(
            bot_self_id or getattr(event, "self_id", "") or ""
        ).strip()
        if not self_id or target_user_id != self_id:
            return False

        group_id = str(
            getattr(event, "group_id", "") or ""
        ).strip()
        if not group_id:
            return False

        duration = max(0, int(getattr(event, "duration", 0) or 0))
        sub_type = str(
            getattr(event, "sub_type", "") or ""
        ).strip().lower()
        muted_until = (
            GroupMuteTracker._now() + duration
            if duration > 0 and sub_type != "lift_ban"
            else 0.0
        )
        GroupMuteTracker.set_group_mute_until(
            group_id, muted_until, source="notice"
        )
        return True


group_mute_tracker = GroupMuteTracker()
"""群禁言状态追踪器单例"""
