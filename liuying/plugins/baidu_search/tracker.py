"""百度搜索配额追踪器

追踪百度智能搜索生成(chat/web_summary)的每日免费额度使用情况，
数据仅存于内存，重启后清零。
"""
import asyncio
from datetime import datetime, timedelta
from typing import Any


class BaiduQuotaTracker:
    """百度搜索配额追踪器

    管理百度 chat/web_summary 模式的每日免费额度，
    web_search 模式不消耗免费额度。
    """

    def __init__(self, daily_limit: int = 100) -> None:
        self._lock = asyncio.Lock()
        self._mode_records: dict[str, int] = {}
        self._daily_limit: int = daily_limit

    def set_daily_limit(self, limit: int) -> None:
        """设置每日免费额度，0 表示不限制"""
        self._daily_limit = max(0, limit)

    async def record(self, mode: str) -> None:
        """记录一次百度搜索调用"""
        async with self._lock:
            self._mode_records[mode] = self._mode_records.get(mode, 0) + 1

    async def is_quota_available(self, mode: str) -> bool:
        """检查剩余免费额度

        web_search 模式不消耗额度，chat 与 web_summary 共享每日额度。
        """
        if mode == "web_search":
            return True
        if self._daily_limit <= 0:
            return True

        async with self._lock:
            chat_used = self._mode_records.get("chat", 0)
            summary_used = self._mode_records.get("web_summary", 0)
            total = chat_used + summary_used
            return total < self._daily_limit

    async def get_quota(self) -> dict[str, Any]:
        """获取配额信息"""
        async with self._lock:
            chat_used = self._mode_records.get("chat", 0)
            summary_used = self._mode_records.get("web_summary", 0)
            used = chat_used + summary_used
            if self._daily_limit > 0:
                remaining = max(0, self._daily_limit - used)
            else:
                remaining = -1
            return {
                "daily_limit": self._daily_limit,
                "used": used,
                "remaining": remaining,
                "reset_in": self._seconds_to_midnight(),
            }

    async def get_mode_summary(self) -> dict[str, dict[str, Any]]:
        """获取各模式使用统计"""
        async with self._lock:
            return {
                mode: {"count": count}
                for mode, count in self._mode_records.items()
            }

    @staticmethod
    def _seconds_to_midnight() -> int:
        """计算距离次日零点的秒数"""
        now = datetime.now()
        midnight = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return max(0, int((midnight - now).total_seconds()))

    async def reset(self) -> None:
        """重置统计"""
        async with self._lock:
            self._mode_records.clear()


baidu_quota_tracker = BaiduQuotaTracker()


__all__ = ["BaiduQuotaTracker", "baidu_quota_tracker"]
