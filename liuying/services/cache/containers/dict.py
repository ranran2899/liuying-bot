"""
缓存字典 - 内存字典容器

提供类似普通字典的接口，数据只存储在内存中。
使用OrderedDict实现O(1)的LRU淘汰策略，
使用最小堆管理过期时间，支持增量清理和定时清理。
同步方法使用 threading.RLock，异步方法使用 AsyncRLock。
"""

from collections import OrderedDict
from dataclasses import dataclass
import heapq
import threading
import time
from typing import Any, Generic, TypeVar

from ..locks import AsyncRLock

T = TypeVar("T")


@dataclass(slots=True)
class CacheData(Generic[T]):
    """缓存数据类，存储数据和过期时间"""

    value: T
    expire_time: float = 0


class CacheDict:
    """缓存字典类，提供类似普通字典的接口，数据只存储在内存中

    使用OrderedDict实现O(1)的LRU淘汰策略（move_to_end），
    使用最小堆管理过期时间，支持增量清理和定时清理，
    避免全量扫描带来的性能损耗。
    同步方法使用 threading.RLock，异步方法使用 AsyncRLock。
    """

    def __init__(self, name: str, expire: int = 0, max_size: int = 0) -> None:
        """初始化缓存字典

        参数:
            name: 字典名称
            expire: 过期时间（秒），默认为0表示永不过期
            max_size: 最大缓存数量，0表示不限制
        """
        self.name = name.upper()
        self.expire = expire
        self.max_size = max_size
        self._data: OrderedDict[str, CacheData[Any]] = OrderedDict()
        self._expire_heap: list[tuple[float, str]] = []
        self._sync_lock = threading.RLock()
        self._async_lock = AsyncRLock()

    def _is_expired(self, data: CacheData[Any], now: float) -> bool:
        """检查数据是否过期

        参数:
            data: 缓存数据
            now: 当前时间戳

        返回:
            bool: 是否过期
        """
        return data.expire_time > 0 and data.expire_time < now

    def _add_expire_entry(self, key: str, expire_time: float) -> None:
        """添加过期条目到堆

        参数:
            key: 缓存键
            expire_time: 过期时间戳
        """
        if expire_time > 0:
            heapq.heappush(self._expire_heap, (expire_time, key))

    def _get_data(self, key: str) -> CacheData[Any] | None:
        """获取数据并检查过期（需在锁内调用）

        参数:
            key: 字典键

        返回:
            CacheData | None: 未过期的数据，否则返回None
        """
        data = self._data.get(key)
        if data is None:
            return None
        if self._is_expired(data, time.time()):
            del self._data[key]
            return None
        return data

    def _evict_lru(self) -> None:
        """LRU淘汰策略（需在锁内调用）

        使用OrderedDict的popitem(last=False)实现O(1)淘汰，
        最早的条目在字典最前面。
        """
        if self.max_size <= 0 or len(self._data) <= self.max_size:
            return
        while len(self._data) > self.max_size:
            self._data.popitem(last=False)

    def _touch_key(self, key: str) -> None:
        """更新访问顺序（需在锁内调用）

        使用move_to_end将访问的键移到末尾，实现O(1)的LRU更新。

        参数:
            key: 缓存键
        """
        self._data.move_to_end(key)

    def _remove_key(self, key: str) -> None:
        """移除键并清理关联数据（需在锁内调用）

        参数:
            key: 缓存键
        """
        self._data.pop(key, None)

    def _set_entry(self, key: str, value: Any, expire: int | None = None) -> None:
        """设置缓存条目（需在锁内调用）

        参数:
            key: 缓存键
            value: 缓存值
            expire: 过期时间（秒），为None时使用默认值
        """
        expire_time = 0
        if expire is not None and expire > 0:
            expire_time = time.time() + expire
        elif self.expire > 0:
            expire_time = time.time() + self.expire
        self._data[key] = CacheData(value=value, expire_time=expire_time)
        self._add_expire_entry(key, expire_time)
        self._touch_key(key)
        self._evict_lru()

    def _clean_expired_incremental(self, batch_size: int = 100) -> int:
        """增量清理过期键，基于最小堆高效获取最早过期的键

        通过比较堆条目的 expire_time 与数据实际的 expire_time，
        跳过因键更新而产生的过期条目，避免内存泄漏。
        当堆大小远大于数据大小时，自动压缩堆以回收空间。

        参数:
            batch_size: 每次清理的最大数量

        返回:
            int: 清理的键数量
        """
        now = time.time()
        cleaned = 0
        while self._expire_heap and cleaned < batch_size:
            expire_time, key = self._expire_heap[0]
            if expire_time > now:
                break
            heapq.heappop(self._expire_heap)
            data = self._data.get(key)
            if data is None:
                continue
            if data.expire_time != expire_time:
                continue
            del self._data[key]
            cleaned += 1
        self._compact_heap()
        return cleaned

    def _compact_heap(self) -> None:
        """压缩过期堆，移除无效条目（需在锁内调用）

        当堆大小超过数据大小的1.5倍时，重建堆以回收空间。
        无效条目包括：键已不存在、过期时间与数据不一致。
        """
        if len(self._expire_heap) <= len(self._data) * 1.5:
            return
        valid_entries: list[tuple[float, str]] = []
        for expire_time, key in self._expire_heap:
            data = self._data.get(key)
            if data is not None and data.expire_time == expire_time:
                valid_entries.append((expire_time, key))
        heapq.heapify(valid_entries)
        self._expire_heap = valid_entries

    def _get_with_touch(self, key: str) -> Any | None:
        """获取数据并更新访问顺序（需在锁内调用）

        参数:
            key: 字典键

        返回:
            Any | None: 数据值或None
        """
        data = self._get_data(key)
        if data is not None:
            self._touch_key(key)
        return data.value if data is not None else None

    async def aget(self, key: str, default: Any = None) -> Any:
        """异步获取字典项

        参数:
            key: 字典键
            default: 默认值

        返回:
            Any: 字典值或默认值
        """
        async with self._async_lock:
            result = self._get_with_touch(key)
            return result if result is not None else default

    async def aset(self, key: str, value: Any, expire: int | None = None) -> None:
        """异步设置字典项

        参数:
            key: 字典键
            value: 字典值
            expire: 过期时间（秒），为None时使用默认值
        """
        async with self._async_lock:
            self._set_entry(key, value, expire)

    async def apop(self, key: str, default: Any = None) -> Any:
        """异步删除并返回字典项

        参数:
            key: 字典键
            default: 默认值

        返回:
            Any: 字典值或默认值
        """
        async with self._async_lock:
            data = self._data.pop(key, None)
            if data is None:
                return default
            if self._is_expired(data, time.time()):
                return default
            return data.value

    async def acontains(self, key: str) -> bool:
        """异步检查键是否存在

        参数:
            key: 字典键

        返回:
            bool: 是否存在
        """
        async with self._async_lock:
            return self._get_data(key) is not None

    async def aclear(self) -> None:
        """异步清空字典"""
        async with self._async_lock:
            self._data.clear()
            self._expire_heap.clear()

    async def akeys(self) -> list[str]:
        """异步获取所有键

        返回:
            list[str]: 键列表
        """
        async with self._async_lock:
            self._clean_expired_incremental()
            return list(self._data.keys())

    async def avalues(self) -> list[Any]:
        """异步获取所有值

        返回:
            list[Any]: 值列表
        """
        async with self._async_lock:
            self._clean_expired_incremental()
            return [data.value for data in self._data.values()]

    async def aitems(self) -> list[tuple[str, Any]]:
        """异步获取所有键值对

        返回:
            list[tuple[str, Any]]: 键值对列表
        """
        async with self._async_lock:
            self._clean_expired_incremental()
            return [(key, data.value) for key, data in self._data.items()]

    async def alen(self) -> int:
        """异步获取字典长度

        返回:
            int: 字典长度
        """
        async with self._async_lock:
            self._clean_expired_incremental()
            return len(self._data)

    def __getitem__(self, key: str) -> Any:
        """获取字典项

        参数:
            key: 字典键

        返回:
            Any: 字典值
        """
        with self._sync_lock:
            return self._get_with_touch(key)

    def __setitem__(self, key: str, value: Any) -> None:
        """设置字典项

        参数:
            key: 字典键
            value: 字典值
        """
        with self._sync_lock:
            self._set_entry(key, value)

    def __delitem__(self, key: str) -> None:
        """删除字典项

        参数:
            key: 字典键
        """
        with self._sync_lock:
            self._remove_key(key)

    def __contains__(self, key: str) -> bool:
        """检查键是否存在

        参数:
            key: 字典键

        返回:
            bool: 是否存在
        """
        with self._sync_lock:
            return self._get_data(key) is not None

    def __len__(self) -> int:
        """获取字典长度

        返回:
            int: 字典长度
        """
        with self._sync_lock:
            return len(self._data)

    def __str__(self) -> str:
        """字符串表示

        返回:
            str: 字符串表示
        """
        with self._sync_lock:
            return (
                f"CacheDict(name={self.name}, expire={self.expire}, "
                f"items={len(self._data)})"
            )

    def get(self, key: str, default: Any = None) -> Any:
        """获取字典项，如果不存在返回默认值

        参数:
            key: 字典键
            default: 默认值

        返回:
            Any: 字典值或默认值
        """
        with self._sync_lock:
            result = self._get_with_touch(key)
            return result if result is not None else default

    def set(self, key: str, value: Any, expire: int | None = None) -> None:
        """设置字典项

        参数:
            key: 字典键
            value: 字典值
            expire: 过期时间（秒），为None时使用默认值
        """
        with self._sync_lock:
            self._set_entry(key, value, expire)

    def pop(self, key: str, default: Any = None) -> Any:
        """删除并返回字典项

        参数:
            key: 字典键
            default: 默认值

        返回:
            Any: 字典值或默认值
        """
        with self._sync_lock:
            data = self._data.pop(key, None)
            if data is None:
                return default
            if self._is_expired(data, time.time()):
                return default
            return data.value

    def clear(self) -> None:
        """清空字典"""
        with self._sync_lock:
            self._data.clear()
            self._expire_heap.clear()

    def keys(self) -> list[str]:
        """获取所有键

        返回:
            list[str]: 键列表
        """
        with self._sync_lock:
            self._clean_expired_incremental()
            return list(self._data.keys())

    def values(self) -> list[Any]:
        """获取所有值

        返回:
            list[Any]: 值列表
        """
        with self._sync_lock:
            self._clean_expired_incremental()
            return [data.value for data in self._data.values()]

    def items(self) -> list[tuple[str, Any]]:
        """获取所有键值对

        返回:
            list[tuple[str, Any]]: 键值对列表
        """
        with self._sync_lock:
            self._clean_expired_incremental()
            return [(key, data.value) for key, data in self._data.items()]

    def cleanup_expired(self, batch_size: int = 100) -> int:
        """手动触发过期数据清理

        参数:
            batch_size: 每次清理的最大数量

        返回:
            int: 清理的键数量
        """
        with self._sync_lock:
            return self._clean_expired_incremental(batch_size)

    async def async_cleanup_expired(self, batch_size: int = 100) -> int:
        """异步触发过期数据清理

        参数:
            batch_size: 每次清理的最大数量

        返回:
            int: 清理的键数量
        """
        async with self._async_lock:
            return self._clean_expired_incremental(batch_size)
