"""
分布式锁实现

提供本地锁和Redis分布式锁的统一接口，
支持单机和分布式部署场景。
"""

from abc import ABC, abstractmethod
import asyncio
import time
from types import TracebackType
from typing import Any, Self
import uuid

from liuying.utils.log import logger

from ..config import LOG_COMMAND


class BaseLock(ABC):
    """锁基类"""

    @abstractmethod
    async def acquire(self, timeout_seconds: float | None = None) -> bool:
        """获取锁

        参数:
            timeout_seconds: 超时时间（秒）

        返回:
            bool: 是否成功获取
        """
        ...

    @abstractmethod
    async def release(self) -> None:
        """释放锁"""
        ...

    @abstractmethod
    def locked(self) -> bool:
        """检查锁是否被占用"""
        ...

    async def __aenter__(self) -> Self:
        await self.acquire()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.release()


class LocalLock(BaseLock):
    """本地异步锁"""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._last_access = time.time()

    async def acquire(self, timeout_seconds: float | None = None) -> bool:
        """获取锁

        参数:
            timeout_seconds: 超时时间（秒）

        返回:
            bool: 是否成功获取
        """
        self._last_access = time.time()
        if timeout_seconds is None:
            await self._lock.acquire()
            return True
        try:
            await asyncio.wait_for(self._lock.acquire(), timeout=timeout_seconds)
            return True
        except TimeoutError:
            return False

    async def release(self) -> None:
        """释放锁

        使用 try-except 而非 locked() 预检查，
        避免当前协程不持有锁时 release 抛出 RuntimeError。
        """
        self._last_access = time.time()
        try:
            self._lock.release()
        except RuntimeError:
            # 锁未被当前协程持有，忽略
            pass

    def locked(self) -> bool:
        """检查锁是否被占用"""
        return self._lock.locked()

    @property
    def last_access(self) -> float:
        """最后访问时间"""
        return self._last_access


class RedisDistributedLock(BaseLock):
    """Redis分布式锁

    使用SET NX EX命令实现分布式锁，
    支持自动过期和锁续期。
    直接接收原生Redis客户端，避免访问aiocache私有属性。
    """

    def __init__(
        self,
        redis_client: Any,
        key: str,
        ttl: int = 30,
    ) -> None:
        self._client = redis_client
        self._key = key
        self._ttl = ttl
        self._token = str(uuid.uuid4())
        self._locked = False
        self._last_access = time.time()

    async def acquire(self, timeout_seconds: float | None = None) -> bool:
        """获取锁

        使用指数退避策略避免高并发下冲击 Redis。
        初始间隔 0.05 秒，每次翻倍，上限 0.5 秒。
        timeout_seconds 为 None 时通过最大重试次数兜底避免无限循环。

        参数:
            timeout_seconds: 超时时间（秒），为None时使用最大重试次数

        返回:
            bool: 是否成功获取
        """
        start_time = time.time()
        delay = 0.05
        max_delay = 0.5
        max_retries_when_no_timeout = 100
        retries = 0

        while True:
            self._last_access = time.time()
            try:
                result = await self._client.set(
                    self._key,
                    self._token,
                    nx=True,
                    ex=self._ttl,
                )
                if result:
                    self._locked = True
                    return True
            except Exception as e:
                logger.debug("Redis锁获取失败，将重试", LOG_COMMAND, e=e)

            if timeout_seconds is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout_seconds:
                    return False
            else:
                retries += 1
                if retries >= max_retries_when_no_timeout:
                    return False

            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)

    async def release(self) -> None:
        """释放锁（使用Lua脚本保证原子性）"""
        self._last_access = time.time()
        if not self._locked:
            return

        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        try:
            await self._client.eval(lua_script, 1, self._key, self._token)
        except Exception as e:
            logger.debug("Redis锁释放失败", LOG_COMMAND, e=e)
        self._locked = False

    def locked(self) -> bool:
        """检查锁是否被占用"""
        return self._locked

    @property
    def last_access(self) -> float:
        """最后访问时间"""
        return self._last_access


class LockManager:
    """锁管理器

    管理本地锁和分布式锁的创建、缓存和清理。
    支持基于时间的自动清理，防止内存泄漏。
    """

    def __init__(
        self,
        lock_ttl: int = 300,
        cleanup_interval: int = 60,
    ) -> None:
        """初始化锁管理器

        参数:
            lock_ttl: 锁默认TTL（秒）
            cleanup_interval: 清理间隔（秒）
        """
        self._locks: dict[str, BaseLock] = {}
        self._lock_ttl = lock_ttl
        self._cleanup_interval = cleanup_interval
        self._redis_client: Any = None
        self._use_distributed = False
        self._release_tasks: set[asyncio.Task] = set()

    @staticmethod
    def _extract_redis_client(backend: Any) -> Any | None:
        """从aiocache后端提取原生Redis客户端

        参数:
            backend: aiocache缓存后端实例

        返回:
            原生Redis客户端或None
        """
        if not hasattr(backend, "_client"):
            return None
        client = backend._client
        if client is not None:
            return client
        try:
            return backend._build_client()
        except Exception:
            return None

    def set_redis_client(self, client: Any) -> None:
        """设置Redis客户端

        参数:
            client: 原生Redis客户端实例
        """
        self._redis_client = client
        self._use_distributed = client is not None

    def init_from_backend(self, backend: Any) -> bool:
        """从缓存后端初始化Redis客户端

        参数:
            backend: aiocache缓存后端实例

        返回:
            bool: 是否成功初始化分布式锁
        """
        client = self._extract_redis_client(backend)
        if client is not None:
            self.set_redis_client(client)
            logger.debug("分布式锁已启用", LOG_COMMAND)
            return True
        return False

    def get_lock(self, key: str) -> BaseLock:
        """获取或创建锁

        参数:
            key: 锁键名

        返回:
            BaseLock: 锁实例
        """
        if key not in self._locks:
            if self._use_distributed and self._redis_client:
                self._locks[key] = RedisDistributedLock(
                    self._redis_client,
                    key,
                    ttl=self._lock_ttl,
                )
            else:
                self._locks[key] = LocalLock()
        return self._locks[key]

    def _schedule_release(self, lock: BaseLock) -> None:
        """安全调度异步锁释放，持有任务引用防止GC回收

        参数:
            lock: 需要释放的锁实例
        """
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(self._safe_release(lock))
            self._release_tasks.add(task)
            task.add_done_callback(self._release_tasks.discard)
        except RuntimeError:
            pass

    @staticmethod
    async def _safe_release(lock: BaseLock) -> None:
        """安全释放锁

        参数:
            lock: 需要释放的锁实例
        """
        try:
            await lock.release()
        except Exception as e:
            logger.debug("异步释放锁失败", LOG_COMMAND, e=e)

    def remove_lock(self, key: str) -> None:
        """移除锁

        参数:
            key: 锁键名
        """
        lock = self._locks.pop(key, None)
        if lock and lock.locked():
            self._schedule_release(lock)

    def cleanup_stale(self, max_age: int = 300) -> int:
        """清理过期锁

        参数:
            max_age: 最大未访问时间（秒）

        返回:
            int: 清理的锁数量
        """
        now = time.time()
        stale_keys = [
            k
            for k, lock in self._locks.items()
            if not lock.locked() and (now - lock.last_access) > max_age
        ]
        for key in stale_keys:
            del self._locks[key]
        return len(stale_keys)

    def clear(self) -> None:
        """清空所有锁"""
        for lock in self._locks.values():
            if lock.locked():
                self._schedule_release(lock)
        self._locks.clear()

    @property
    def lock_count(self) -> int:
        """当前锁数量"""
        return len(self._locks)
