"""
缓存列表 - 内存列表容器

提供类似普通列表的接口，数据只存储在内存中。
同步方法使用 threading.RLock，异步方法使用 AsyncRLock。
"""

import threading
import time
from typing import Any, overload

from ..locks import AsyncRLock
from .dict import CacheData


class CacheList:
    """缓存列表类，提供类似普通列表的接口，数据只存储在内存中

    同步方法使用 threading.RLock，异步方法使用 AsyncRLock。
    """

    def __init__(self, name: str, expire: int = 0, max_size: int = 0) -> None:
        """初始化缓存列表

        参数:
            name: 列表名称
            expire: 过期时间（秒），默认为0表示永不过期
            max_size: 最大元素数量，0表示不限制
        """
        self.name = name.upper()
        self.expire = expire
        self.max_size = max_size
        self._data: CacheData[list[Any]] = CacheData(value=[], expire_time=0)
        self._sync_lock = threading.RLock()
        self._async_lock = AsyncRLock()

    def _check_expire(self) -> None:
        """检查是否过期（需在锁内调用）"""
        now = time.time()
        if (
            self.expire > 0
            and self._data.expire_time > 0
            and self._data.expire_time < now
        ):
            self._data.value.clear()
            self._data.expire_time = 0

    def _check_max_size(self) -> None:
        """检查并移除超出限制的元素（需在锁内调用）"""
        if self.max_size > 0 and len(self._data.value) > self.max_size:
            overflow = len(self._data.value) - self.max_size
            del self._data.value[:overflow]

    def _update_expire_time(self) -> None:
        """更新过期时间（需在锁内调用）"""
        if self.expire > 0:
            self._data.expire_time = time.time() + self.expire

    @overload
    def __getitem__(self, index: int) -> Any: ...

    @overload
    def __getitem__(self, index: slice) -> list[Any]: ...

    def __getitem__(self, index: int | slice) -> Any | list[Any]:
        """获取列表项，支持索引和切片

        参数:
            index: 索引或切片

        返回:
            Any | list[Any]: 列表项或切片结果
        """
        with self._sync_lock:
            self._check_expire()
            return self._data.value[index]

    @overload
    def __setitem__(self, index: int, value: Any) -> None: ...

    @overload
    def __setitem__(self, index: slice, value: Any) -> None: ...

    def __setitem__(self, index: int | slice, value: Any) -> None:
        """设置列表项

        参数:
            index: 索引或切片
            value: 值
        """
        with self._sync_lock:
            self._check_expire()
            self._data.value[index] = value
            self._update_expire_time()

    def __delitem__(self, index: int | slice) -> None:
        """删除列表项

        参数:
            index: 索引或切片
        """
        with self._sync_lock:
            self._check_expire()
            del self._data.value[index]
            self._update_expire_time()

    def __len__(self) -> int:
        """获取列表长度

        返回:
            int: 列表长度
        """
        with self._sync_lock:
            self._check_expire()
            return len(self._data.value)

    def __contains__(self, value: Any) -> bool:
        """检查值是否在列表中

        参数:
            value: 值

        返回:
            bool: 是否存在
        """
        with self._sync_lock:
            self._check_expire()
            return value in self._data.value

    def __str__(self) -> str:
        """字符串表示

        返回:
            str: 字符串表示
        """
        with self._sync_lock:
            return (
                f"CacheList(name={self.name}, expire={self.expire}, "
                f"items={len(self._data.value)})"
            )

    def append(self, value: Any) -> None:
        """添加列表项

        参数:
            value: 值
        """
        with self._sync_lock:
            self._check_expire()
            self._data.value.append(value)
            self._check_max_size()
            self._update_expire_time()

    def extend(self, values: list[Any]) -> None:
        """扩展列表

        参数:
            values: 值列表
        """
        with self._sync_lock:
            self._check_expire()
            self._data.value.extend(values)
            self._check_max_size()
            self._update_expire_time()

    def insert(self, index: int, value: Any) -> None:
        """插入列表项

        参数:
            index: 索引
            value: 值
        """
        with self._sync_lock:
            self._check_expire()
            self._data.value.insert(index, value)
            self._check_max_size()
            self._update_expire_time()

    def pop(self, index: int = -1) -> Any:
        """删除并返回列表项

        参数:
            index: 索引，默认为-1

        返回:
            Any: 列表项
        """
        with self._sync_lock:
            self._check_expire()
            value = self._data.value.pop(index)
            self._update_expire_time()
            return value

    def remove(self, value: Any) -> None:
        """删除列表项

        参数:
            value: 值
        """
        with self._sync_lock:
            self._check_expire()
            self._data.value.remove(value)
            self._update_expire_time()

    def clear(self) -> None:
        """清空列表"""
        with self._sync_lock:
            self._data.value = []
            self._data.expire_time = 0

    def index(self, value: Any, start: int = 0, end: int | None = None) -> int:
        """查找值索引

        参数:
            value: 值
            start: 起始位置
            end: 结束位置

        返回:
            int: 索引
        """
        with self._sync_lock:
            self._check_expire()
            args: list[Any] = [value, start]
            if end is not None:
                args.append(end)
            return self._data.value.index(*args)

    def count(self, value: Any) -> int:
        """统计值出现次数

        参数:
            value: 值

        返回:
            int: 出现次数
        """
        with self._sync_lock:
            self._check_expire()
            return self._data.value.count(value)

    def sort(self, key: Any = None, reverse: bool = False) -> None:
        """排序列表

        参数:
            key: 排序键
            reverse: 是否逆序
        """
        with self._sync_lock:
            self._check_expire()
            self._data.value.sort(key=key, reverse=reverse)
            self._update_expire_time()

    def reverse(self) -> None:
        """反转列表"""
        with self._sync_lock:
            self._check_expire()
            self._data.value.reverse()
            self._update_expire_time()

    async def aappend(self, value: Any) -> None:
        """异步添加列表项

        参数:
            value: 值
        """
        async with self._async_lock:
            self._check_expire()
            self._data.value.append(value)
            self._check_max_size()
            self._update_expire_time()

    async def aextend(self, values: list[Any]) -> None:
        """异步扩展列表

        参数:
            values: 值列表
        """
        async with self._async_lock:
            self._check_expire()
            self._data.value.extend(values)
            self._check_max_size()
            self._update_expire_time()

    async def ainsert(self, index: int, value: Any) -> None:
        """异步插入列表项

        参数:
            index: 索引
            value: 值
        """
        async with self._async_lock:
            self._check_expire()
            self._data.value.insert(index, value)
            self._check_max_size()
            self._update_expire_time()

    async def apop(self, index: int = -1) -> Any:
        """异步删除并返回列表项

        参数:
            index: 索引，默认为-1

        返回:
            Any: 列表项
        """
        async with self._async_lock:
            self._check_expire()
            value = self._data.value.pop(index)
            self._update_expire_time()
            return value

    async def aremove(self, value: Any) -> None:
        """异步删除列表项

        参数:
            value: 值
        """
        async with self._async_lock:
            self._check_expire()
            self._data.value.remove(value)
            self._update_expire_time()

    async def aclear(self) -> None:
        """异步清空列表"""
        async with self._async_lock:
            self._data.value = []
            self._data.expire_time = 0

    async def alen(self) -> int:
        """异步获取列表长度

        返回:
            int: 列表长度
        """
        async with self._async_lock:
            self._check_expire()
            return len(self._data.value)

    async def acontains(self, value: Any) -> bool:
        """异步检查值是否在列表中

        参数:
            value: 值

        返回:
            bool: 是否存在
        """
        async with self._async_lock:
            self._check_expire()
            return value in self._data.value

    async def aget(self, index: int) -> Any:
        """异步获取列表项

        参数:
            index: 索引

        返回:
            Any: 列表项
        """
        async with self._async_lock:
            self._check_expire()
            return self._data.value[index]

    async def aset(self, index: int, value: Any) -> None:
        """异步设置列表项

        参数:
            index: 索引
            value: 值
        """
        async with self._async_lock:
            self._check_expire()
            self._data.value[index] = value
            self._update_expire_time()

    async def async_cleanup_expired(self, batch_size: int = 100) -> int:
        """异步触发过期检查，回收过期列表内存

        CacheList 的过期是整体过期（非逐条），过期后清空整个列表。
        此方法供后台定时任务调用，避免长时间不访问的过期列表占用内存。

        参数:
            batch_size: 为保持与 CacheDict 接口一致的参数（忽略）

        返回:
            int: 清理的条目数（过期时返回列表长度，否则0）
        """
        async with self._async_lock:
            old_len = len(self._data.value)
            self._check_expire()
            new_len = len(self._data.value)
            return old_len - new_len
