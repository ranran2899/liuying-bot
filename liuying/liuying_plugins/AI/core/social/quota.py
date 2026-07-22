"""社交智能配额

每用户每日上限 + 单场景冷却，防止bot被当成骚扰。
使用内存缓存存储，重启后重新累计。

数据结构：
{
    "<YYYY-MM-DD>": {
        "<user_id>": {"<scenario>": [ts, ts, ...], "total": int}
    }
}
"""

from datetime import datetime
import threading
import time
from typing import Any

__all__ = ["SocialQuota", "social_quota"]


_KEEP_DAYS = 14
"""日志保留天数"""


class SocialQuota:
    """社交智能配额管理器

    封装主动社交消息的配额检查与记录。
    所有状态存储在内存中，重启后重新积累。

    配额策略：
    - 每用户每日总配额上限
    - 单场景冷却时间
    - 自动清理过期日志（保留14天）
    """

    def __init__(self) -> None:
        """初始化配额管理器"""
        self._log: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _today_str(now: float | None = None) -> str:
        """获取今日日期字符串

        参数:
            now: 时间戳，None用当前时间

        返回:
            str: 日期字符串（YYYY-MM-DD）
        """
        ts = float(
            now if now is not None else time.time()
        )
        return datetime.fromtimestamp(ts).strftime(
            "%Y-%m-%d"
        )

    def is_quota_exceeded(
        self,
        user_id: str,
        *,
        scenario: str,
        daily_quota_per_user: int,
        cooldown_seconds: int,
        now: float | None = None,
    ) -> bool:
        """检查是否超过配额

        参数:
            user_id: 用户ID
            scenario: 场景名称
            daily_quota_per_user: 每用户每日配额
            cooldown_seconds: 单场景冷却时间（秒）
            now: 当前时间戳

        返回:
            bool: True表示超过配额
        """
        uid = str(user_id).strip()
        if not uid:
            return True
        quota = max(0, int(daily_quota_per_user or 0))
        if quota <= 0:
            return True
        cd = max(0, int(cooldown_seconds or 0))
        now_ts = float(
            now if now is not None else time.time()
        )
        with self._lock:
            today_log = self._log.get(
                self._today_str(now_ts), {}
            )
            user_log = today_log.get(uid, {})
            total = int(user_log.get("total", 0) or 0)
            if total >= quota:
                return True
            if cd > 0:
                timestamps = (
                    user_log.get(scenario, []) or []
                )
                if isinstance(timestamps, list) and timestamps:
                    last_val = timestamps[-1]
                    if isinstance(
                        last_val, int | float
                    ) and not isinstance(last_val, bool):
                        last = float(last_val)
                    else:
                        last = 0.0
                    if now_ts - last < cd:
                        return True
            return False

    def mark_sent(
        self,
        user_id: str,
        *,
        scenario: str,
        now: float | None = None,
    ) -> None:
        """标记已发送一条主动消息

        参数:
            user_id: 用户ID
            scenario: 场景名称
            now: 当前时间戳
        """
        uid = str(user_id).strip()
        if not uid:
            return
        now_ts = float(
            now if now is not None else time.time()
        )
        today = self._today_str(now_ts)
        with self._lock:
            today_log = self._log.setdefault(today, {})
            user_log = today_log.setdefault(uid, {})
            timestamps = user_log.setdefault(scenario, [])
            if not isinstance(timestamps, list):
                timestamps = []
                user_log[scenario] = timestamps
            timestamps.append(now_ts)
            user_log["total"] = (
                int(user_log.get("total", 0) or 0) + 1
            )
            self._prune_old_days()

    def _prune_old_days(
        self, keep_days: int = _KEEP_DAYS
    ) -> None:
        """清理过期日志

        参数:
            keep_days: 保留天数
        """
        keys = sorted(self._log.keys())
        if len(keys) <= keep_days:
            return
        for k in keys[: len(keys) - keep_days]:
            self._log.pop(k, None)


social_quota = SocialQuota()
"""社交配额管理器单例"""
