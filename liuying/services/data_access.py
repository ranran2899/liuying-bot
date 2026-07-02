"""
数据访问层模块

提供带缓存的数据访问接口，支持自动缓存管理和批量操作优化。
"""

from typing import Any, ClassVar, Generic, TypeVar, cast

from liuying.services.cache import CacheRoot, cache_config
from liuying.services.cache.config import COMPOSITE_KEY_SEPARATOR, CacheMode
from liuying.services.liuying_db import DbUtils, Model
from liuying.utils.log import logger

T = TypeVar("T", bound=Model)


class CacheStats:
    """缓存统计数据类"""

    __slots__ = ("deletes", "hits", "misses", "null_hits", "null_sets", "sets")

    def __init__(self) -> None:
        self.hits: int = 0
        self.misses: int = 0
        self.null_hits: int = 0
        self.sets: int = 0
        self.null_sets: int = 0
        self.deletes: int = 0

    def to_dict(self) -> dict[str, int]:
        """转换为字典"""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "null_hits": self.null_hits,
            "sets": self.sets,
            "null_sets": self.null_sets,
            "deletes": self.deletes,
        }

    def reset(self) -> None:
        """重置统计"""
        self.hits = 0
        self.misses = 0
        self.null_hits = 0
        self.sets = 0
        self.null_sets = 0
        self.deletes = 0


class DataAccess(Generic[T]):
    """数据访问层，根据配置决定是否使用缓存

    使用示例:
    ```python
    from liuying.services import DataAccess
    from liuying.models.plugin_info import PluginInfo

    plugin_dao = DataAccess(PluginInfo)

    plugin = await plugin_dao.get_or_none(module="example_module")
    all_plugins = await plugin_dao.all()
    enabled_plugins = await plugin_dao.filter(status=True)
    new_plugin = await plugin_dao.create(
        module="new_module", name="新插件", status=True
    )
    ```
    """

    _cache_stats: ClassVar[dict[str, CacheStats]] = {}
    _NULL_RESULT = "__NULL_RESULT_PLACEHOLDER__"
    _NULL_RESULT_TTL = 300

    @classmethod
    def set_null_result_ttl(cls, seconds: int) -> None:
        """设置空结果缓存时间

        参数:
            seconds: 缓存时间（秒）
        """
        if seconds < 0:
            raise ValueError("缓存时间不能为负数")
        cls._NULL_RESULT_TTL = seconds
        logger.info(f"已设置DataAccess空结果缓存时间为 {seconds} 秒")

    @classmethod
    def get_null_result_ttl(cls) -> int:
        """获取空结果缓存时间

        返回:
            int: 缓存时间（秒）
        """
        return cls._NULL_RESULT_TTL

    def __init__(
        self, model_cls: type[T], key_field: str = "id", cache_type: str | None = None
    ) -> None:
        """初始化数据访问对象

        参数:
            model_cls: 模型类
            key_field: 主键字段
            cache_type: 缓存类型
        """
        self.model_cls = model_cls
        self.key_field = getattr(model_cls, "cache_key_field", key_field)
        self.cache_type = getattr(model_cls, "cache_type", cache_type)

        if not self.cache_type:
            raise ValueError("缓存类型不能为空")

        if self.cache_type not in self._cache_stats:
            self._cache_stats[self.cache_type] = CacheStats()

    def _get_stats(self) -> CacheStats:
        """获取当前缓存类型的统计对象"""
        return self._cache_stats[self.cache_type]

    @classmethod
    def get_cache_stats(cls) -> list[dict[str, Any]]:
        """获取缓存统计信息

        返回:
            list[dict[str, Any]]: 统计信息列表
        """
        result = []
        for cache_type, stats in cls._cache_stats.items():
            total = stats.hits + stats.null_hits + stats.misses
            if total > 0:
                hit_rate = (stats.hits + stats.null_hits) / total * 100
            else:
                hit_rate = 0
            result.append(
                {
                    "cache_type": cache_type,
                    **stats.to_dict(),
                    "hit_rate": f"{hit_rate:.2f}%",
                }
            )
        return result

    @classmethod
    def reset_cache_stats(cls) -> None:
        """重置缓存统计信息"""
        for stats in cls._cache_stats.values():
            stats.reset()

    def _build_key_from_values(self, values: dict[str, Any]) -> str | None:
        """从值字典构建缓存键

        参数:
            values: 字段值字典

        返回:
            str | None: 缓存键
        """
        if isinstance(self.key_field, tuple):
            key_parts = [str(values.get(field, "")) for field in self.key_field]
            return COMPOSITE_KEY_SEPARATOR.join(key_parts) if key_parts else None

        if self.key_field in values:
            return str(values[self.key_field])
        return None

    def _build_cache_key_from_kwargs(self, **kwargs: Any) -> str | None:
        """从关键字参数构建缓存键

        参数:
            **kwargs: 关键字参数

        返回:
            str | None: 缓存键
        """
        return self._build_key_from_values(kwargs)

    def _build_cache_key_for_item(self, item: T) -> str | None:
        """为数据项构建缓存键

        参数:
            item: 数据项

        返回:
            str | None: 缓存键
        """
        if isinstance(self.key_field, tuple):
            values = {field: getattr(item, field, "") for field in self.key_field}
        else:
            value = getattr(item, self.key_field, None)
            values = {self.key_field: value} if value is not None else {}

        return self._build_key_from_values(values)

    async def _set_cache(
        self, cache_key: str, data: Any, expire: int | None = None
    ) -> bool:
        """设置缓存并更新统计

        参数:
            cache_key: 缓存键
            data: 缓存数据
            expire: 过期时间

        返回:
            bool: 是否成功
        """
        try:
            await CacheRoot.set(self.cache_type, cache_key, data, expire)
            stats = self._get_stats()
            if data == self._NULL_RESULT:
                stats.null_sets += 1
            else:
                stats.sets += 1
            return True
        except Exception as e:
            logger.error(f"{self.model_cls.__name__} 设置缓存失败: {cache_key}", e=e)
            return False

    async def _delete_cache(self, cache_key: str) -> bool:
        """删除缓存并更新统计

        参数:
            cache_key: 缓存键

        返回:
            bool: 是否成功
        """
        try:
            await CacheRoot.delete(self.cache_type, cache_key)
            self._get_stats().deletes += 1
            return True
        except Exception as e:
            logger.error(f"{self.model_cls.__name__} 删除缓存失败: {cache_key}", e=e)
            return False

    def _is_cache_enabled(self) -> bool:
        """检查缓存是否启用"""
        return bool(self.cache_type and cache_config.cache_mode != CacheMode.NONE)

    async def _try_get_from_cache(
        self, cache_key: str
    ) -> tuple[Any | None, bool, bool]:
        """尝试从缓存获取数据

        参数:
            cache_key: 缓存键

        返回:
            tuple[Any | None, bool, bool]: (数据, 是否命中, 是否为空结果)
        """
        try:
            data = await CacheRoot.get(self.cache_type, cache_key)
            if data == self._NULL_RESULT:
                return None, True, True
            if data is not None:
                return data, True, False
            return None, False, False
        except Exception as e:
            logger.error(f"{self.model_cls.__name__} 获取缓存失败: {cache_key}", e=e)
            return None, False, False

    async def _get_with_cache(
        self,
        db_query_func: Any,
        allow_not_exist: bool = True,
        *args: Any,
        **kwargs: Any,
    ) -> T | None:
        """带缓存的通用获取方法

        参数:
            db_query_func: 数据库查询函数
            allow_not_exist: 是否允许数据不存在
            *args: 查询参数
            **kwargs: 查询参数

        返回:
            T | None: 查询结果
        """
        if not self._is_cache_enabled():
            return await DbUtils.with_db_timeout(
                db_query_func(*args, **kwargs),
                operation=f"{self.model_cls.__name__}.{db_query_func.__name__}",
                source="DataAccess",
            )

        cache_key = self._build_cache_key_from_kwargs(**kwargs)
        stats = self._get_stats()

        if cache_key is not None:
            data, hit, is_null = await self._try_get_from_cache(cache_key)

            if hit:
                if is_null:
                    stats.null_hits += 1
                    return None if allow_not_exist else None
                stats.hits += 1
                return cast(T, data)

            stats.misses += 1

        data = await db_query_func(*args, **kwargs)

        if data:
            item_key = self._build_cache_key_for_item(data)
            if item_key:
                await self._set_cache(item_key, data)
        elif cache_key is not None:
            await self._set_cache(cache_key, self._NULL_RESULT, self._NULL_RESULT_TTL)

        return data

    async def get_or_none(
        self, allow_not_exist: bool = True, *args: Any, **kwargs: Any
    ) -> T | None:
        """获取单条数据

        参数:
            allow_not_exist: 是否允许数据不存在
            *args: 查询参数
            **kwargs: 查询参数

        返回:
            T | None: 查询结果
        """
        return await self._get_with_cache(
            self.model_cls.filter(*args, **kwargs).first, allow_not_exist, **kwargs
        )

    async def safe_get_or_none(
        self, allow_not_exist: bool = True, *args: Any, **kwargs: Any
    ) -> T | None:
        """安全的获取单条数据

        参数:
            allow_not_exist: 是否允许数据不存在
            *args: 查询参数
            **kwargs: 查询参数

        返回:
            T | None: 查询结果
        """
        return await self._get_with_cache(
            self.model_cls.safe_get_or_none, allow_not_exist, *args, **kwargs
        )

    async def get_by_func_or_none(
        self, func: Any, allow_not_exist: bool = True, *args: Any, **kwargs: Any
    ) -> T | None:
        """根据函数获取数据

        参数:
            func: 查询函数
            allow_not_exist: 是否允许数据不存在
            *args: 查询参数
            **kwargs: 查询参数

        返回:
            T | None: 查询结果
        """
        return await self._get_with_cache(func, allow_not_exist, *args, **kwargs)

    async def clear_cache(self, **kwargs: Any) -> bool:
        """清除缓存

        参数:
            **kwargs: 查询参数

        返回:
            bool: 是否成功
        """
        if not self._is_cache_enabled():
            return True

        cache_key = self._build_cache_key_from_kwargs(**kwargs)
        if cache_key is None:
            logger.warning(f"{self.model_cls.__name__} 清除缓存失败: 缺少主键字段")
            return False

        return await self._delete_cache(cache_key)

    async def _cache_items(self, data_list: list[T]) -> int:
        """批量缓存数据列表

        参数:
            data_list: 数据列表

        返回:
            int: 成功缓存的数量
        """
        if not data_list or not self._is_cache_enabled():
            return 0

        items: dict[str, T] = {}
        for item in data_list:
            cache_key = self._build_cache_key_for_item(item)
            if cache_key:
                items[cache_key] = item

        if not items:
            return 0

        try:
            result = await CacheRoot.multi_set_pipeline(self.cache_type, items)
            self._get_stats().sets += result.succeeded
            return result.succeeded
        except Exception as e:
            logger.error(f"{self.model_cls.__name__} 批量缓存失败", e=e)
            return 0

    async def _delete_caches(self, cache_keys: list[str]) -> int:
        """批量删除缓存

        参数:
            cache_keys: 缓存键列表

        返回:
            int: 成功删除的数量
        """
        if not cache_keys or not self._is_cache_enabled():
            return 0

        try:
            result = await CacheRoot.multi_delete(self.cache_type, cache_keys)
            self._get_stats().deletes += result.succeeded
            return result.succeeded
        except Exception as e:
            logger.error(f"{self.model_cls.__name__} 批量删除缓存失败", e=e)
            return 0

    async def filter(self, *args: Any, **kwargs: Any) -> list[T]:
        """筛选数据

        参数:
            *args: 查询参数
            **kwargs: 查询参数

        返回:
            list[T]: 查询结果列表
        """
        data_list = await self.model_cls.filter(*args, **kwargs).all()
        await self._cache_items(data_list)
        return data_list

    async def all(self) -> list[T]:
        """获取所有数据

        返回:
            list[T]: 所有数据列表
        """
        data_list = await self.model_cls.filter().all()
        await self._cache_items(data_list)
        return data_list

    async def count(self, *args: Any, **kwargs: Any) -> int:
        """获取数据数量

        参数:
            *args: 查询参数
            **kwargs: 查询参数

        返回:
            int: 数据数量
        """
        return await self.model_cls.filter(*args, **kwargs).count()

    async def exists(self, *args: Any, **kwargs: Any) -> bool:
        """判断数据是否存在

        参数:
            *args: 查询参数
            **kwargs: 查询参数

        返回:
            bool: 是否存在
        """
        return await self.model_cls.filter(*args, **kwargs).exists()

    async def create(self, **kwargs: Any) -> T:
        """创建数据

        参数:
            **kwargs: 创建参数

        返回:
            T: 创建的数据
        """
        data = await self.model_cls.create(**kwargs)

        if self._is_cache_enabled():
            cache_key = self._build_cache_key_for_item(data)
            if cache_key:
                await self._set_cache(cache_key, data)

        return data

    async def update_or_create(
        self, defaults: dict[str, Any] | None = None, **kwargs: Any
    ) -> tuple[T, bool]:
        """更新或创建数据

        参数:
            defaults: 默认值
            **kwargs: 查询参数

        返回:
            tuple[T, bool]: (数据, 是否创建)
        """
        data, created = await self.model_cls.update_or_create(
            defaults=defaults, **kwargs
        )

        if self._is_cache_enabled():
            cache_key = self._build_cache_key_for_item(data)
            if cache_key:
                await self._set_cache(cache_key, data)

        return data, created

    async def delete(self, *args: Any, **kwargs: Any) -> int:
        """删除数据

        参数:
            *args: 查询参数
            **kwargs: 查询参数

        返回:
            int: 删除的数据数量
        """
        cache_keys_to_delete: list[str] = []

        if self._is_cache_enabled():
            cache_key = self._build_cache_key_from_kwargs(**kwargs)
            if cache_key:
                cache_keys_to_delete.append(cache_key)
            else:
                items = await self.model_cls.filter(*args, **kwargs).all()
                for item in items:
                    item_key = self._build_cache_key_for_item(item)
                    if item_key:
                        cache_keys_to_delete.append(item_key)

            if cache_keys_to_delete:
                await self._delete_caches(cache_keys_to_delete)

        return await self.model_cls.filter(*args, **kwargs).delete()
