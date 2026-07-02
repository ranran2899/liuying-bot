"""
缓存预热操作

批量加载数据到缓存中，用于启动时预热热点数据。
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from liuying.utils.log import logger

from ..config import LOG_COMMAND, CacheMode, KeyType, cache_config
from .operations import CacheOperations
from .registry import TypeRegistry


@dataclass(slots=True)
class WarmupResult:
    """预热结果"""

    total: int
    """总条目数"""
    succeeded: int
    """成功数"""
    failed: int
    """失败数"""
    errors: list[str]
    """错误信息列表"""

    @property
    def success(self) -> bool:
        """是否全部成功"""
        return self.failed == 0


class WarmupExecutor:
    """缓存预热执行器

    批量加载数据到缓存中，用于启动时预热热点数据。
    持有缓存操作执行器、类型注册器和启用状态依赖。
    loader 接口约定:keys 为 None 时无参调用 await loader()，
    keys 不为 None 时按 key 调用 await loader(key)。
    """

    def __init__(
        self,
        cache_ops: CacheOperations,
        registry: TypeRegistry,
        enabled: bool,
    ) -> None:
        """初始化预热执行器

        参数:
            cache_ops: 缓存单条操作执行器
            registry: 类型注册器
            enabled: 缓存是否启用
        """
        self._cache_ops = cache_ops
        self._registry = registry
        self._enabled = enabled

    def set_enabled(self, enabled: bool) -> None:
        """设置预热启用状态

        参数:
            enabled: 是否启用
        """
        self._enabled = enabled

    async def _warmup_single(
        self,
        cache_type: str,
        key: KeyType,
        loader: Callable[..., Any],
        expire: int | None,
    ) -> bool:
        """预热单个缓存项

        loader 在 keys 模式下按约定接收 key 参数。

        参数:
            cache_type: 缓存类型
            key: 缓存键
            loader: 数据加载函数
            expire: 过期时间

        返回:
            bool: 是否成功
        """
        try:
            data = await loader(key)
            if data is None:
                return False
            return await self._cache_ops.set(cache_type, key, data, expire)
        except Exception as e:
            logger.warning(f"预热缓存失败: {cache_type}:{key}", LOG_COMMAND, e=e)
            return False

    async def warmup(
        self,
        cache_type: str,
        loader: Callable[..., Any],
        keys: list[KeyType] | None = None,
        expire: int | None = None,
        batch_size: int | None = None,
    ) -> WarmupResult:
        """缓存预热

        批量加载数据到缓存中，用于启动时预热热点数据。

        参数:
            cache_type: 缓存类型
            loader: 数据加载函数，接收key参数，返回数据
            keys: 要预热的键列表，为None时由loader自行决定加载哪些数据
            expire: 过期时间（秒）
            batch_size: 批量大小，为None时使用配置值

        返回:
            WarmupResult: 预热结果
        """
        if not self._enabled or cache_config.cache_mode == CacheMode.NONE:
            return WarmupResult(total=0, succeeded=0, failed=0, errors=["缓存未启用"])

        resolved_type = cache_type.upper()
        if not self._registry.is_valid(resolved_type):
            return WarmupResult(
                total=0, succeeded=0, failed=0, errors=["缓存类型未注册"]
            )

        batch = batch_size or cache_config.warmup_batch_size
        errors: list[str] = []
        succeeded = 0
        failed = 0

        if keys is None:
            try:
                data = await loader()
                match data:
                    case dict():
                        items = data
                    case list():
                        items = dict(enumerate(data))
                    case _:
                        items = {"default": data}

                set_results = await asyncio.gather(
                    *(
                        self._cache_ops.set(
                            resolved_type,
                            k if isinstance(k, str) else str(k),
                            v,
                            expire,
                        )
                        for k, v in items.items()
                    ),
                    return_exceptions=True,
                )
                for result in set_results:
                    match result:
                        case Exception() as e:
                            errors.append(str(e))
                            failed += 1
                        case True:
                            succeeded += 1
                        case _:
                            failed += 1
            except Exception as e:
                errors.append(str(e))
                failed = 1
        else:
            total_keys = len(keys)
            for i in range(0, total_keys, batch):
                batch_keys = keys[i : i + batch]
                tasks = [
                    self._warmup_single(
                        resolved_type,
                        key,
                        loader,
                        expire,
                    )
                    for key in batch_keys
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for j, result in enumerate(results):
                    match result:
                        case Exception():
                            errors.append(f"{batch_keys[j]}: {result}")
                            failed += 1
                        case True:
                            succeeded += 1
                        case _:
                            failed += 1

        logger.info(
            f"缓存预热完成: {resolved_type}, 成功: {succeeded}, 失败: {failed}",
            LOG_COMMAND,
        )

        return WarmupResult(
            total=succeeded + failed,
            succeeded=succeeded,
            failed=failed,
            errors=errors,
        )
