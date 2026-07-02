"""
缓存类型注册器

支持命名空间隔离，用于多租户场景。
支持键TTL跟踪，防止内存泄漏。
"""

import time
from typing import Any

from liuying.utils.log import logger

from ..config import (
    CACHE_KEY_PREFIX,
    CACHE_KEY_SEPARATOR,
    LOG_COMMAND,
    NAMESPACE_SEPARATOR,
    CacheException,
    cache_config,
)
from ..models import CacheModel


class TypeRegistry:
    """缓存类型注册器

    管理缓存类型的注册、查询和键构建。
    支持命名空间隔离，用于多租户场景。
    支持键TTL跟踪，定期清理过期键记录，防止内存泄漏。
    """

    def __init__(self, namespace: str = "") -> None:
        """初始化类型注册器

        参数:
            namespace: 命名空间，用于多租户隔离
        """
        self._registry: dict[str, CacheModel] = {}
        self._type_keys: dict[str, set[str]] = {}
        self._key_ttl: dict[str, float] = {}
        self._key_to_type: dict[str, str] = {}
        self._namespace = namespace or cache_config.namespace

    @property
    def namespace(self) -> str:
        """获取当前命名空间"""
        return self._namespace

    @namespace.setter
    def namespace(self, value: str) -> None:
        """设置命名空间

        参数:
            value: 新的命名空间
        """
        self._namespace = value

    def set_namespace(self, namespace: str) -> None:
        """设置命名空间（用于运行时切换租户）

        参数:
            namespace: 命名空间
        """
        self._namespace = namespace

    def clear_namespace(self) -> None:
        """清除命名空间"""
        self._namespace = ""

    def register(
        self,
        name: str,
        result_type: type | None = None,
        expire: int = 600,
        key_format: str | None = None,
    ) -> None:
        """注册缓存类型

        参数:
            name: 缓存名称
            result_type: 结果类型
            expire: 过期时间（秒）
            key_format: 键格式
        """
        name = name.upper()
        if name in self._registry:
            logger.warning(f"缓存类型 {name} 已存在，将被覆盖", LOG_COMMAND)

        self._registry[name] = CacheModel.create(
            name=name,
            result_type=result_type,
            expire=expire,
            key_format=key_format,
        )
        self._type_keys.setdefault(name, set())
        logger.debug(
            f"注册缓存类型: {name}, 类型: {result_type}, 过期时间: {expire}秒",
            LOG_COMMAND,
        )

    def get_model(self, name: str) -> CacheModel:
        """获取缓存模型

        参数:
            name: 缓存名称

        返回:
            CacheModel: 缓存模型

        异常:
            CacheException: 缓存类型不存在
        """
        name = name.upper()
        if name not in self._registry:
            raise CacheException("缓存类型不存在", cache_type=name)
        return self._registry[name]

    def is_valid(self, cache_type: str) -> bool:
        """检查缓存类型是否已注册

        参数:
            cache_type: 缓存类型

        返回:
            bool: 是否已注册
        """
        return cache_type.upper() in self._registry

    def build_key(
        self,
        cache_type: str,
        key: str | dict[str, Any],
        namespace: str | None = None,
    ) -> str:
        """构建缓存键

        参数:
            cache_type: 缓存类型
            key: 键或键参数
            namespace: 可选的命名空间，覆盖默认命名空间

        返回:
            str: 完整缓存键
        """
        cache_type = cache_type.upper()
        model = self.get_model(cache_type)

        match key:
            case dict():
                key_value = self._format_dict_key(cache_type, key, model.key_format)
            case _:
                key_value = str(key)

        ns = namespace if namespace is not None else self._namespace
        return self._build_full_key(cache_type, key_value, ns)

    def _format_dict_key(
        self, cache_type: str, key: dict[str, Any], key_format: str | None
    ) -> str:
        """格式化字典类型的缓存键

        参数:
            cache_type: 缓存类型
            key: 字典键参数
            key_format: 键格式模板

        返回:
            str: 格式化后的键值

        异常:
            CacheException: 键格式错误时抛出
        """
        if key_format:
            try:
                return key_format.format(**key)
            except KeyError as e:
                raise CacheException(
                    f"键格式错误: {key_format}, 缺少参数: {e}",
                    cache_type=cache_type,
                    key=key,
                )
        return "_".join(str(key[k]) for k in sorted(key.keys()) if key[k] is not None)

    def _build_full_key(
        self, cache_type: str, key_value: str, namespace: str | None = None
    ) -> str:
        """构建完整缓存键（包含前缀和命名空间）

        参数:
            cache_type: 缓存类型
            key_value: 键值
            namespace: 命名空间

        返回:
            str: 完整缓存键
        """
        parts = [CACHE_KEY_PREFIX]

        ns = namespace if namespace is not None else self._namespace
        if ns:
            parts.append(ns)

        parts.append(cache_type)
        parts.append(key_value)

        return CACHE_KEY_SEPARATOR.join(parts)

    def build_key_with_namespace(
        self, cache_type: str, key: str | dict[str, Any], namespace: str
    ) -> str:
        """构建带指定命名空间的缓存键

        参数:
            cache_type: 缓存类型
            key: 键或键参数
            namespace: 命名空间

        返回:
            str: 完整缓存键
        """
        return self.build_key(cache_type, key, namespace)

    def parse_namespace_from_key(self, cache_key: str) -> str | None:
        """从缓存键中解析命名空间

        参数:
            cache_key: 完整缓存键

        返回:
            str | None: 命名空间，如果不存在返回None
        """
        parts = cache_key.split(CACHE_KEY_SEPARATOR)
        if len(parts) >= 3 and NAMESPACE_SEPARATOR not in parts[1]:
            if parts[1] != CACHE_KEY_PREFIX and parts[1] not in self._registry:
                return parts[1]
        return None

    def add_key(self, cache_type: str, cache_key: str, ttl: int | None = None) -> None:
        """添加缓存键到类型键集合，同时记录TTL

        参数:
            cache_type: 缓存类型
            cache_key: 完整缓存键
            ttl: 过期时间（秒），为None时使用缓存类型的默认过期时间
        """
        self._type_keys.setdefault(cache_type, set()).add(cache_key)
        self._key_to_type[cache_key] = cache_type
        if ttl is None:
            model = self._registry.get(cache_type)
            ttl = model.expire if model else cache_config.redis_expire
        if ttl and ttl > 0:
            self._key_ttl[cache_key] = time.time() + ttl

    def remove_key(self, cache_type: str, cache_key: str) -> None:
        """从类型键集合中移除缓存键

        参数:
            cache_type: 缓存类型
            cache_key: 完整缓存键
        """
        self._type_keys.get(cache_type, set()).discard(cache_key)
        self._key_ttl.pop(cache_key, None)
        self._key_to_type.pop(cache_key, None)

    def get_keys(self, cache_type: str) -> set[str]:
        """获取指定类型的所有缓存键

        参数:
            cache_type: 缓存类型

        返回:
            set[str]: 缓存键集合
        """
        return self._type_keys.get(cache_type, set())

    def pop_keys(self, cache_type: str) -> set[str]:
        """弹出指定类型的所有缓存键

        参数:
            cache_type: 缓存类型

        返回:
            set[str]: 缓存键集合
        """
        keys = self._type_keys.pop(cache_type, set())
        for key in keys:
            self._key_ttl.pop(key, None)
            self._key_to_type.pop(key, None)
        return keys

    def clear_all_keys(self) -> None:
        """清除所有类型键集合"""
        self._type_keys.clear()
        self._key_ttl.clear()
        self._key_to_type.clear()

    def get_keys_by_namespace(self, namespace: str) -> dict[str, set[str]]:
        """获取指定命名空间的所有缓存键

        参数:
            namespace: 命名空间

        返回:
            dict[str, set[str]]: 按类型分组的缓存键
        """
        result: dict[str, set[str]] = {}
        ns_prefix = (
            f"{CACHE_KEY_PREFIX}{CACHE_KEY_SEPARATOR}"
            f"{namespace}{CACHE_KEY_SEPARATOR}"
        )
        for cache_type, keys in self._type_keys.items():
            ns_keys = {k for k in keys if k.startswith(ns_prefix)}
            if ns_keys:
                result[cache_type] = ns_keys
        return result

    def clear_namespace_keys(self, namespace: str) -> int:
        """清除指定命名空间的所有缓存键

        参数:
            namespace: 命名空间

        返回:
            int: 清除的键数量
        """
        total_cleared = 0
        ns_prefix = (
            f"{CACHE_KEY_PREFIX}{CACHE_KEY_SEPARATOR}"
            f"{namespace}{CACHE_KEY_SEPARATOR}"
        )
        for cache_type in list(self._type_keys.keys()):
            keys = self._type_keys[cache_type]
            ns_keys = {k for k in keys if k.startswith(ns_prefix)}
            if ns_keys:
                self._type_keys[cache_type] = keys - ns_keys
                for key in ns_keys:
                    self._key_ttl.pop(key, None)
                    self._key_to_type.pop(key, None)
                total_cleared += len(ns_keys)
        return total_cleared

    def cleanup_expired_keys(self, batch_size: int = 1000) -> int:
        """清理过期的键记录

        根据TTL记录清理已过期的键，防止_type_keys无限增长。
        使用反向索引实现O(1)键到类型的查找。

        参数:
            batch_size: 每次清理的最大数量

        返回:
            int: 清理的键数量
        """
        if not self._key_ttl:
            return 0

        now = time.time()
        expired_keys = sorted(
            (key for key, expire_time in self._key_ttl.items() if expire_time <= now),
            key=lambda k: self._key_ttl[k],
        )

        cleaned = 0
        for key in expired_keys[:batch_size]:
            self._key_ttl.pop(key, None)
            cache_type = self._key_to_type.pop(key, None)
            if cache_type is not None:
                type_keys = self._type_keys.get(cache_type)
                if type_keys is not None and key in type_keys:
                    type_keys.discard(key)
                    cleaned += 1

        if cleaned > 0:
            logger.debug(f"清理过期键记录: {cleaned}条", LOG_COMMAND)

        return cleaned

    @property
    def registered_count(self) -> int:
        """已注册的缓存类型数量

        返回:
            int: 类型数量
        """
        return len(self._registry)

    @property
    def all_cache_keys(self) -> set[str]:
        """获取所有缓存键

        返回:
            set[str]: 所有缓存键集合
        """
        return {k for keys in self._type_keys.values() for k in keys}

    @property
    def total_keys_count(self) -> int:
        """获取所有键的总数

        返回:
            int: 键总数
        """
        return sum(len(keys) for keys in self._type_keys.values())

    @property
    def ttl_keys_count(self) -> int:
        """获取有TTL记录的键数量

        返回:
            int: 有TTL记录的键数量
        """
        return len(self._key_ttl)
