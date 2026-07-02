"""网络搜索使用次数追踪器 - 轻量级内存统计

按搜索引擎(provider) 与百度搜索模式(mode) 维度统计搜索调用次数，
数据仅存于内存，重启后清零。每日免费额度由配置项 BAIDU_DAILY_LIMIT 控制，
超出后 record 仍会记录，但调用方可通过 is_baidu_quota_available 预检。
"""
import asyncio
from datetime import datetime, timedelta
from typing import Any


class SearchUsageRecord:
    """单条搜索使用记录"""

    __slots__ = ("count", "last_used")

    def __init__(self) -> None:
        """初始化记录"""
        self.count: int = 0
        self.last_used: datetime | None = None

    def add(self) -> None:
        """累加一次调用统计"""
        self.count += 1
        self.last_used = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """转换为字典

        返回:
            统计字典
        """
        return {
            "count": self.count,
            "last_used": self.last_used.isoformat() if self.last_used else None,
        }


class SearchUsageTracker:
    """网络搜索使用次数追踪器

    按搜索引擎与百度搜索模式维度统计调用次数，并提供基于每日免费额度的
    配额预检能力。
    """

    def __init__(self) -> None:
        """初始化追踪器"""
        self._lock = asyncio.Lock()
        self._provider_records: dict[str, SearchUsageRecord] = {}
        self._baidu_mode_records: dict[str, SearchUsageRecord] = {}
        self._daily_limit: int = 100

    def set_daily_limit(self, limit: int) -> None:
        """设置百度智能搜索生成每日免费额度

        参数:
            limit: 每日免费额度，0 表示不限制
        """
        self._daily_limit = max(0, limit)

    async def record(self, provider: str, mode: str | None = None) -> None:
        """记录一次搜索调用

        参数:
            provider: 搜索引擎名称 (如 baidu/bocha)
            mode: 百度搜索模式 (web_search/chat/web_summary)，
                  非 baidu 引擎可为 None
        """
        async with self._lock:
            if provider not in self._provider_records:
                self._provider_records[provider] = SearchUsageRecord()
            self._provider_records[provider].add()

            if provider == "baidu" and mode:
                if mode not in self._baidu_mode_records:
                    self._baidu_mode_records[mode] = SearchUsageRecord()
                self._baidu_mode_records[mode].add()

    async def is_baidu_quota_available(self, mode: str) -> bool:
        """检查百度智能搜索生成剩余免费额度

        仅 chat / web_summary 模式受每日免费额度限制，
        web_search 模式不消耗免费额度。

        参数:
            mode: 百度搜索模式

        返回:
            True 表示仍有免费额度或额度不限制
        """
        if mode == "web_search":
            return True
        if self._daily_limit <= 0:
            return True

        async with self._lock:
            record = self._baidu_mode_records.get(mode)
            used = record.count if record else 0
            # chat 与 web_summary 共享每日 100 次免费额度
            if mode in ("chat", "web_summary"):
                chat_used = self._baidu_mode_records.get("chat")
                summary_used = self._baidu_mode_records.get("web_summary")
                total = (chat_used.count if chat_used else 0) + (
                    summary_used.count if summary_used else 0
                )
                return total < self._daily_limit
            return used < self._daily_limit

    async def get_provider_summary(self) -> dict[str, dict[str, Any]]:
        """按搜索引擎获取统计摘要

        返回:
            搜索引擎名到统计字典的映射
        """
        async with self._lock:
            return {
                name: record.to_dict()
                for name, record in self._provider_records.items()
            }

    async def get_baidu_mode_summary(self) -> dict[str, dict[str, Any]]:
        """按百度搜索模式获取统计摘要

        返回:
            模式名到统计字典的映射
        """
        async with self._lock:
            return {
                name: record.to_dict()
                for name, record in self._baidu_mode_records.items()
            }

    async def get_total(self) -> dict[str, Any]:
        """获取全局总计

        返回:
            全局统计字典
        """
        async with self._lock:
            total_count = sum(r.count for r in self._provider_records.values())
            last_used: datetime | None = None
            for record in self._provider_records.values():
                if record.last_used and (
                    last_used is None or record.last_used > last_used
                ):
                    last_used = record.last_used
            return {
                "count": total_count,
                "last_used": last_used.isoformat() if last_used else None,
                "daily_limit": self._daily_limit,
            }

    async def get_baidu_quota(self) -> dict[str, Any]:
        """获取百度智能搜索生成剩余配额信息

        返回:
            包含每日额度、已用、剩余的字典
        """
        async with self._lock:
            chat_used = self._baidu_mode_records.get("chat")
            summary_used = self._baidu_mode_records.get("web_summary")
            used = (chat_used.count if chat_used else 0) + (
                summary_used.count if summary_used else 0
            )
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

    @staticmethod
    def _seconds_to_midnight() -> int:
        """计算距离次日零点的秒数

        返回:
            秒数
        """
        now = datetime.now()
        midnight = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return max(0, int((midnight - now).total_seconds()))

    async def reset(self) -> None:
        """重置所有统计"""
        async with self._lock:
            self._provider_records.clear()
            self._baidu_mode_records.clear()


search_tracker = SearchUsageTracker()


__all__ = ["SearchUsageTracker", "search_tracker"]
