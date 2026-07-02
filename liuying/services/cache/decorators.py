"""
缓存装饰器
"""

from collections.abc import Callable
from functools import wraps
from typing import Any

from liuying.utils.log import logger

from .config import DEFAULT_EXPIRE, LOG_COMMAND, CacheMode, cache_config
from .core.manager import CacheRoot


class CacheKeyBuilder:
    """缓存键构建器

    提供缓存键的构建逻辑，处理键构建函数的异常和默认值。
    """

    @staticmethod
    def build(
        key_builder: Callable[..., Any] | None,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        """构建缓存键

        参数:
            key_builder: 键构建函数
            args: 位置参数
            kwargs: 关键字参数

        返回:
            Any: 缓存键
        """
        if not key_builder:
            return None
        try:
            return key_builder(*args, **kwargs)
        except Exception as e:
            logger.warning("构建缓存键失败", LOG_COMMAND, e=e)
            return None


async def _get_or_load_and_set(
    cache_type: str,
    cache_key: Any,
    func: Callable,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    expire: int,
) -> Any:
    """获取缓存，未命中则执行函数并设置缓存

    参数:
        cache_type: 缓存类型
        cache_key: 缓存键
        func: 原始函数
        args: 位置参数
        kwargs: 关键字参数
        expire: 过期时间（秒）

    返回:
        Any: 缓存数据或函数执行结果
    """
    try:
        cached_result = await CacheRoot.get(cache_type, cache_key)
        if cached_result is not None:
            return cached_result
    except Exception as e:
        logger.warning("获取缓存失败", LOG_COMMAND, e=e)

    result = await func(*args, **kwargs)

    try:
        await CacheRoot.set(cache_type, cache_key, result, expire)
    except Exception as e:
        logger.warning("设置缓存失败", LOG_COMMAND, e=e)

    return result


def cached(
    cache_type: str,
    key_builder: Callable[..., Any] | None = None,
    expire: int = DEFAULT_EXPIRE,
    skip_cache: Callable[..., bool] | None = None,
) -> Callable:
    """缓存装饰器 - 自动缓存函数结果

    参数:
        cache_type: 缓存类型
        key_builder: 键构建函数，接收函数参数，返回缓存键
        expire: 过期时间（秒）
        skip_cache: 判断是否跳过缓存的函数，返回True时跳过缓存

    示例:
        ```python
        from liuying.services.cache import cached

        @cached("USER", key_builder=lambda user_id: {"user_id": user_id})
        async def get_user(user_id: str):
            return await User.get(user_id)
        ```
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if cache_config.cache_mode == CacheMode.NONE:
                return await func(*args, **kwargs)

            # 没有 key_builder 无法构建唯一缓存键，直接执行函数避免键冲突
            if not key_builder:
                return await func(*args, **kwargs)

            cache_key = CacheKeyBuilder.build(key_builder, args, kwargs)
            if cache_key is None:
                return await func(*args, **kwargs)

            if skip_cache and skip_cache(*args, **kwargs):
                return await func(*args, **kwargs)

            return await _get_or_load_and_set(
                cache_type, cache_key, func, args, kwargs, expire
            )

        return wrapper

    return decorator


def cache_evict(
    cache_type: str,
    key_builder: Callable[..., Any] | None = None,
) -> Callable:
    """缓存清除装饰器 - 函数执行后清除缓存

    参数:
        cache_type: 缓存类型
        key_builder: 键构建函数，接收函数参数，返回缓存键

    示例:
        ```python
        from liuying.services.cache import cache_evict

        @cache_evict("USER", key_builder=lambda user_id: {"user_id": user_id})
        async def update_user(user_id: str, data: dict):
            return await User.update(user_id, data)
        ```
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = await func(*args, **kwargs)

            if cache_config.cache_mode == CacheMode.NONE:
                return result

            cache_key = CacheKeyBuilder.build(key_builder, args, kwargs)
            if key_builder and cache_key is not None:
                try:
                    await CacheRoot.delete(cache_type, cache_key)
                except Exception as e:
                    logger.warning("清除缓存失败", LOG_COMMAND, e=e)

            return result

        return wrapper

    return decorator


def cache_put(
    cache_type: str,
    key_builder: Callable[..., Any] | None = None,
    expire: int = DEFAULT_EXPIRE,
) -> Callable:
    """缓存更新装饰器 - 函数执行后更新缓存

    参数:
        cache_type: 缓存类型
        key_builder: 键构建函数，接收函数参数和返回值，返回缓存键
        expire: 过期时间（秒）

    示例:
        ```python
        from liuying.services.cache import cache_put

        @cache_put("USER", key_builder=lambda user_id, **kwargs: {"user_id": user_id})
        async def create_user(user_id: str, name: str):
            user = await User.create(user_id=user_id, name=name)
            return user
        ```
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = await func(*args, **kwargs)

            if cache_config.cache_mode == CacheMode.NONE:
                return result

            cache_key = CacheKeyBuilder.build(key_builder, args, kwargs)
            if key_builder and cache_key is not None:
                try:
                    await CacheRoot.set(cache_type, cache_key, result, expire)
                except Exception as e:
                    logger.warning("更新缓存失败", LOG_COMMAND, e=e)

            return result

        return wrapper

    return decorator


def cache_all(cache_type: str, expire: int = DEFAULT_EXPIRE) -> Callable:
    """缓存所有结果装饰器 - 缓存函数的所有调用结果

    参数:
        cache_type: 缓存类型
        expire: 过期时间（秒）

    示例:
        ```python
        from liuying.services.cache import cache_all

        @cache_all("CONFIG")
        async def get_config():
            return await Config.get_all()
        ```
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if cache_config.cache_mode == CacheMode.NONE:
                return await func(*args, **kwargs)

            # 使用 __qualname__ 避免不同模块同名函数共享缓存
            return await _get_or_load_and_set(
                cache_type, func.__qualname__, func, args, kwargs, expire
            )

        return wrapper

    return decorator
