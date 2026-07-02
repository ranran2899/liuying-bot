"""
缓存访问接口

提供类型化的缓存访问接口，支持命名空间隔离、Pipeline操作和预热。
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from .config import CacheException, KeyType
from .core.manager import CacheRoot

if TYPE_CHECKING:
    from .core.batch import BatchResult
    from .core.warmup import WarmupResult

T = TypeVar("T")


class Cache(Generic[T]):
    """类型化缓存访问接口

    示例:
        ```python
        from liuying.services.cache import Cache

        level_cache = Cache("LEVEL", result_type=list[UserLevel])

        users = await level_cache.get({"user_id": "123", "group_id": "456"})
        await level_cache.set({"user_id": "123", "group_id": "456"}, users)

        users = await level_cache.get_or_load(
            {"user_id": "123", "group_id": "456"},
            loader=lambda: fetch_users("123", "456"),
        )
        ```
    """

    def __init__(self, cache_type: str, result_type: type | None = None) -> None:
        """初始化缓存访问对象

        参数:
            cache_type: 缓存类型
            result_type: 结果类型，显式指定时优先使用
        """
        self.cache_type = cache_type.upper()
        self._result_type = result_type
        self._cache_root = CacheRoot

        resolved_type = result_type or self._resolve_generic_type()
        if resolved_type is not None:
            try:
                CacheRoot.get_model(self.cache_type)
            except CacheException:
                CacheRoot.register(self.cache_type, resolved_type)

    def _resolve_generic_type(self) -> type | None:
        """从泛型参数中解析结果类型

        返回:
            type | None: 解析到的结果类型
        """
        orig_class = getattr(self, "__orig_class__", None)
        if orig_class is not None and hasattr(orig_class, "__args__"):
            return orig_class.__args__[0]
        return None

    async def get(
        self,
        key: KeyType,
        default: T | None = None,
        namespace: str | None = None,
    ) -> T | None:
        """获取缓存数据

        参数:
            key: 键或键参数
            default: 默认值
            namespace: 可选的命名空间

        返回:
            T | None: 缓存数据，如果不存在返回默认值
        """
        return await self._cache_root.get(self.cache_type, key, default, namespace)

    async def get_or_load(
        self,
        key: KeyType,
        loader: Callable[..., Any],
        expire: int | None = None,
        default: T | None = None,
        namespace: str | None = None,
    ) -> T | None:
        """带击穿防护的获取缓存数据，缓存未命中时通过loader加载

        参数:
            key: 键或键参数
            loader: 数据加载函数（异步）
            expire: 过期时间（秒）
            default: 默认值
            namespace: 可选的命名空间

        返回:
            T | None: 缓存数据或loader加载的数据
        """
        return await self._cache_root.get_with_stampede(
            self.cache_type, key, loader, expire, default, namespace
        )

    async def set(
        self,
        key: KeyType,
        value: T,
        expire: int | None = None,
        namespace: str | None = None,
    ) -> bool:
        """设置缓存数据

        参数:
            key: 键或键参数
            value: 值
            expire: 过期时间（秒），为None时使用默认值
            namespace: 可选的命名空间

        返回:
            bool: 是否成功
        """
        return await self._cache_root.set(
            self.cache_type, key, value, expire, namespace
        )

    async def delete(self, key: KeyType) -> bool:
        """删除缓存数据

        参数:
            key: 键或键参数

        返回:
            bool: 是否成功
        """
        return await self._cache_root.delete(self.cache_type, key)

    async def exists(self, key: KeyType) -> bool:
        """检查缓存是否存在

        参数:
            key: 键或键参数

        返回:
            bool: 是否存在
        """
        return await self._cache_root.exists(self.cache_type, key)

    async def clear(self) -> bool:
        """清除此类型的所有缓存

        返回:
            bool: 是否成功
        """
        return await self._cache_root.clear(self.cache_type)

    async def raw_get(
        self,
        key: str,
        default: T | None = None,
        namespace: str | None = None,
    ) -> T | None:
        """获取原始键缓存数据

        参数:
            key: 原始缓存键
            default: 默认值
            namespace: 可选的命名空间

        返回:
            T | None: 缓存数据，如果不存在返回默认值
        """
        return await self._cache_root.raw_get(key, default, namespace)

    async def raw_set(
        self,
        key: str,
        value: T,
        expire: int | None = None,
        namespace: str | None = None,
    ) -> bool:
        """设置原始键缓存数据

        参数:
            key: 原始缓存键
            value: 值
            expire: 过期时间（秒）
            namespace: 可选的命名空间

        返回:
            bool: 是否成功
        """
        return await self._cache_root.raw_set(key, value, expire, namespace)

    async def raw_delete(self, key: str, namespace: str | None = None) -> bool:
        """删除原始键缓存数据

        参数:
            key: 原始缓存键
            namespace: 可选的命名空间

        返回:
            bool: 是否成功
        """
        return await self._cache_root.raw_delete(key, namespace)

    async def raw_exists(self, key: str, namespace: str | None = None) -> bool:
        """检查原始键缓存是否存在

        参数:
            key: 原始缓存键
            namespace: 可选的命名空间

        返回:
            bool: 是否存在
        """
        return await self._cache_root.raw_exists(key, namespace)

    async def multi_get(self, keys: list[KeyType]) -> "BatchResult":
        """批量获取缓存数据

        参数:
            keys: 键列表

        返回:
            BatchResult: 批量操作结果，包含成功/失败统计和详细结果
        """
        return await self._cache_root.multi_get(self.cache_type, keys)

    async def multi_set(
        self, items: dict[KeyType, T], expire: int | None = None
    ) -> "BatchResult":
        """批量设置缓存数据

        参数:
            items: 键值对字典
            expire: 过期时间（秒）

        返回:
            BatchResult: 批量操作结果，包含成功/失败统计
        """
        return await self._cache_root.multi_set(self.cache_type, items, expire)

    async def multi_delete(self, keys: list[KeyType]) -> "BatchResult":
        """批量删除缓存数据

        参数:
            keys: 键列表

        返回:
            BatchResult: 批量操作结果，包含成功/失败统计
        """
        return await self._cache_root.multi_delete(self.cache_type, keys)

    async def multi_get_pipeline(self, keys: list[KeyType]) -> "BatchResult":
        """使用Pipeline批量获取缓存数据

        仅在Redis模式下使用Pipeline优化，其他模式回退到普通批量获取。

        参数:
            keys: 键列表

        返回:
            BatchResult: 批量操作结果
        """
        return await self._cache_root.multi_get_pipeline(self.cache_type, keys)

    async def multi_set_pipeline(
        self, items: dict[KeyType, T], expire: int | None = None
    ) -> "BatchResult":
        """使用Pipeline批量设置缓存数据

        仅在Redis模式下使用Pipeline优化，其他模式回退到普通批量设置。

        参数:
            items: 键值对字典
            expire: 过期时间（秒）

        返回:
            BatchResult: 批量操作结果
        """
        return await self._cache_root.multi_set_pipeline(self.cache_type, items, expire)

    async def warmup(
        self,
        loader: Callable[..., Any],
        keys: list[KeyType] | None = None,
        expire: int | None = None,
        batch_size: int | None = None,
    ) -> "WarmupResult":
        """缓存预热

        批量加载数据到缓存中，用于启动时预热热点数据。

        参数:
            loader: 数据加载函数，接收key参数，返回数据
            keys: 要预热的键列表，为None时由loader自行决定加载哪些数据
            expire: 过期时间（秒）
            batch_size: 批量大小

        返回:
            WarmupResult: 预热结果
        """
        return await self._cache_root.warmup(
            self.cache_type, loader, keys, expire, batch_size
        )
