"""网络搜索使用次数追踪器 - 轻量级内存统计

按搜索引擎(provider) 与搜索模式(mode) 维度统计搜索调用次数，
数据仅存于内存，重启后清零。
"""
import asyncio
from datetime import datetime
from typing import Any


class SearchUsageRecord:
    """单条搜索使用记录"""

    __slots__ = ("count", "last_used")

    def __init__(self) -> None:
        self.count: int = 0
        self.last_used: datetime | None = None

    def add(self) -> None:
        self.count += 1
        self.last_used = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "last_used": self.last_used.isoformat() if self.last_used else None,
        }


class SearchUsageTracker:
    """网络搜索使用次数追踪器

    按搜索引擎与搜索模式维度统计调用次数。
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._provider_records: dict[str, SearchUsageRecord] = {}
        self._mode_records: dict[str, dict[str, SearchUsageRecord]] = {}

    async def record(self, provider: str, mode: str | None = None) -> None:
        """记录一次搜索调用

        参数:
            provider: 搜索引擎名称
            mode: 搜索模式标识，可为 None
        """
        async with self._lock:
            if provider not in self._provider_records:
                self._provider_records[provider] = SearchUsageRecord()
            self._provider_records[provider].add()

            if mode:
                if provider not in self._mode_records:
                    self._mode_records[provider] = {}
                if mode not in self._mode_records[provider]:
                    self._mode_records[provider][mode] = SearchUsageRecord()
                self._mode_records[provider][mode].add()

    async def get_provider_summary(self) -> dict[str, dict[str, Any]]:
        """按搜索引擎获取统计摘要"""
        async with self._lock:
            return {
                name: record.to_dict()
                for name, record in self._provider_records.items()
            }

    async def get_mode_summary(
        self, provider: str | None = None
    ) -> dict[str, dict[str, dict[str, Any]]]:
        """按搜索模式获取统计摘要

        参数:
            provider: 指定引擎则只返回该引擎的模式统计，None 返回全部

        返回:
            provider -> mode -> 统计字典
        """
        async with self._lock:
            if provider:
                return {
                    provider: {
                        mode: record.to_dict()
                        for mode, record in self._mode_records.get(provider, {}).items()
                    }
                }
            return {
                name: {
                    mode: record.to_dict()
                    for mode, record in modes.items()
                }
                for name, modes in self._mode_records.items()
            }

    async def get_total(self) -> dict[str, Any]:
        """获取全局总计"""
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
            }

    async def reset(self) -> None:
        """重置所有统计"""
        async with self._lock:
            self._provider_records.clear()
            self._mode_records.clear()


search_tracker = SearchUsageTracker()


__all__ = ["SearchUsageTracker", "search_tracker"]
