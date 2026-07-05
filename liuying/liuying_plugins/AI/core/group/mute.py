"""群禁言感知

双通道更新禁言状态：被动监听 group_ban notice 事件 +
主动调用 get_group_member_info 查询 shut_up_timestamp。
30秒本地缓存避免重复请求。
"""

import time
from typing import Any, ClassVar

from liuying.services.cache import CacheDict
from liuying.utils.log import logger

__all__ = ["GroupMuteTracker", "group_mute_tracker"]


class GroupMuteTracker:
    """群禁言状态追踪器

    封装群禁言状态的设置、查询、notice更新与主动刷新能力，
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

    @staticmethod
    async def refresh_bot_group_mute_state(
        bot: Any,
        group_id: str,
        *,
        ttl_seconds: float = 30.0,
    ) -> bool:
        """主动刷新Bot在群的禁言状态

        带30秒TTL缓存，避免重复请求。

        参数:
            bot: Bot对象
            group_id: 群组ID
            ttl_seconds: 缓存TTL秒数

        返回:
            bool: 是否处于禁言期
        """
        gid = str(group_id)
        now_value = GroupMuteTracker._now()

        cached = GroupMuteTracker._mute_state_cache.get(gid)
        if cached:
            checked_at = float(
                cached.get("checked_at", 0.0) or 0.0
            )
            if now_value - checked_at <= max(
                0.0, float(ttl_seconds)
            ):
                return float(
                    cached.get("muted_until", 0.0) or 0.0
                ) > now_value

        self_id = str(getattr(bot, "self_id", "") or "0")
        try:
            info = await bot.get_group_member_info(
                group_id=int(gid),
                user_id=int(self_id),
                no_cache=True,
            )
        except TypeError:
            try:
                info = await bot.get_group_member_info(
                    group_id=int(gid),
                    user_id=int(self_id),
                )
            except Exception as exc:
                logger.debug(
                    f"获取群成员信息失败: {exc}",
                    command="AI",
                    e=exc,
                    group_id=gid,
                )
                return GroupMuteTracker.is_group_muted(gid)
        except Exception as exc:
            logger.debug(
                f"获取群成员信息失败: {exc}",
                command="AI",
                e=exc,
                group_id=gid,
            )
            return GroupMuteTracker.is_group_muted(gid)

        muted_until = float(
            (info or {}).get("shut_up_timestamp", 0) or 0.0
        )
        GroupMuteTracker.set_group_mute_until(
            gid, muted_until, source="member_info"
        )
        return muted_until > now_value


group_mute_tracker = GroupMuteTracker()
"""群禁言状态追踪器单例"""
