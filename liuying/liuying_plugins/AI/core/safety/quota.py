"""配额管理

每用户每日主动消息配额管理。
按群和用户维度计数，内存字典按天重置。
"""

from dataclasses import dataclass
from datetime import date

from liuying.utils.log import logger

from ...config import get_config

__all__ = ["QuotaManager", "quota_manager"]


@dataclass(slots=True)
class _QuotaEntry:
    """配额计数条目

    Attributes:
        date: 当前计数日期
        count: 已使用配额数
    """

    date: date
    count: int = 0


class QuotaManager:
    """配额管理器

    每用户每日主动消息配额，按群+用户维度计数。
    内存字典存储，跨天自动重置。
    """

    _DEFAULT_DAILY_QUOTA: int = 5
    """默认每用户每日配额"""

    def __init__(self) -> None:
        """初始化配额管理器"""
        self._entries: dict[tuple[str, str], _QuotaEntry] = {}
        """(group_id, user_id) -> 配额条目"""

    def _get_entry(
        self, user_id: str, group_id: str
    ) -> _QuotaEntry:
        """获取配额条目，跨天重置

        参数:
            user_id: 用户ID
            group_id: 群组ID

        返回:
            _QuotaEntry: 配额条目
        """
        key = (group_id, user_id)
        today = date.today()
        entry = self._entries.get(key)
        if entry is None or entry.date != today:
            entry = _QuotaEntry(date=today, count=0)
            self._entries[key] = entry
        return entry

    def _get_daily_limit(self) -> int:
        """获取每日配额上限

        返回:
            int: 每日配额上限
        """
        limit = get_config(
            "PROACTIVE_USER_DAILY_QUOTA",
            self._DEFAULT_DAILY_QUOTA,
        )
        try:
            limit_int = int(limit)
            return max(0, limit_int)
        except (TypeError, ValueError):
            return self._DEFAULT_DAILY_QUOTA

    def check_quota(
        self, user_id: str, group_id: str
    ) -> bool:
        """检查用户配额是否可用

        参数:
            user_id: 用户ID
            group_id: 群组ID

        返回:
            bool: 配额是否可用
        """
        if not user_id or not group_id:
            return False
        entry = self._get_entry(user_id, group_id)
        remaining = self._get_daily_limit() - entry.count
        if remaining <= 0:
            logger.debug(
                f"用户 {user_id} 群 {group_id} "
                f"主动消息配额已用尽",
                command="AI",
            )
            return False
        return True

    def consume(
        self, user_id: str, group_id: str
    ) -> None:
        """消耗一次配额

        参数:
            user_id: 用户ID
            group_id: 群组ID
        """
        if not user_id or not group_id:
            return
        entry = self._get_entry(user_id, group_id)
        entry.count += 1
        logger.debug(
            f"用户 {user_id} 群 {group_id} "
            f"消耗主动消息配额，累计 {entry.count}",
            command="AI",
        )

    def get_remaining(
        self, user_id: str, group_id: str
    ) -> int:
        """获取剩余配额

        参数:
            user_id: 用户ID
            group_id: 群组ID

        返回:
            int: 剩余配额数
        """
        if not user_id or not group_id:
            return 0
        entry = self._get_entry(user_id, group_id)
        return max(
            0, self._get_daily_limit() - entry.count
        )


quota_manager = QuotaManager()
"""配额管理器单例"""
