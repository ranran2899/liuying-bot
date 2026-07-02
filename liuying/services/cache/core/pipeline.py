"""
缓存 Pipeline 批量操作

仅在 Redis 模式下使用 Pipeline 优化批量获取和设置
"""

from typing import Any

from liuying.utils.log import logger

from ..config import LOG_COMMAND, CacheMode, KeyType, cache_config
from ..serializer import CacheSerializer
from .backend import BackendManager
from .batch import BatchExecutor, BatchResult
from .operations import CacheOperations
from .registry import TypeRegistry


class PipelineExecutor:
    """Pipeline 批量操作执行器

    仅在 Redis 模式下使用 Pipeline 优化批量获取和设置，
    其他模式回退到普通批量操作。持有后端、注册器、批量执行器依赖。
    """

    def __init__(
        self,
        backend_mgr: BackendManager,
        registry: TypeRegistry,
        batch_executor: BatchExecutor,
    ) -> None:
        """初始化 Pipeline 执行器

        参数:
            backend_mgr: 后端管理器
            registry: 类型注册器
            batch_executor: 批量操作执行器（回退时使用）
        """
        self._backend_mgr = backend_mgr
        self._registry = registry
        self._batch_executor = batch_executor

    @staticmethod
    def _check_available() -> bool:
        """检查是否满足 Pipeline 执行条件

        返回:
            bool: 是否启用 Pipeline 且为 Redis 模式
        """
        return (
            cache_config.enable_pipeline
            and cache_config.cache_mode == CacheMode.REDIS
        )

    async def multi_get(
        self,
        cache_type: str,
        keys: list[KeyType],
        get_func: Any,
    ) -> BatchResult:
        """使用 Pipeline 批量获取缓存数据

        仅在 Redis 模式下使用 Pipeline 优化，其他模式回退到普通批量获取。

        参数:
            cache_type: 缓存类型
            keys: 键列表
            get_func: 单条获取函数（回退时使用）

        返回:
            BatchResult: 批量操作结果
        """
        if not self._check_available():
            return await self._batch_executor.multi_get(
                cache_type, keys, get_func
            )

        redis_client = self._backend_mgr.redis_client
        if redis_client is None:
            return await self._batch_executor.multi_get(
                cache_type, keys, get_func
            )

        resolved_type = cache_type.upper()
        if not self._registry.is_valid(resolved_type):
            return self._batch_executor.make_disabled_result(
                len(keys), "缓存类型未注册"
            )

        results: dict[str, Any] = {}
        errors: dict[str, str] = {}
        succeeded = 0
        failed = 0
        model = self._registry.get_model(resolved_type)
        result_type = model.result_type
        batch_size = cache_config.pipeline_batch_size

        cache_keys_map = {
            self._registry.build_key(resolved_type, key): key for key in keys
        }
        cache_keys = list(cache_keys_map.keys())

        for i in range(0, len(cache_keys), batch_size):
            batch_keys = cache_keys[i : i + batch_size]
            try:
                pipe = redis_client.pipeline(transaction=False)
                for cache_key in batch_keys:
                    pipe.get(cache_key)
                values = await pipe.execute()

                for idx, value in enumerate(values):
                    cache_key = batch_keys[idx]
                    match value:
                        case Exception():
                            errors[cache_key] = str(value)
                            failed += 1
                        case None:
                            results[cache_key] = None
                            succeeded += 1
                        case _:
                            results[cache_key] = CacheSerializer.deserialize(
                                value,
                                result_type,
                            )
                            succeeded += 1
            except Exception as e:
                for cache_key in batch_keys:
                    errors[cache_key] = str(e)
                    failed += 1
                logger.warning("Pipeline批量获取失败", LOG_COMMAND, e=e)

        return BatchResult(
            success=failed == 0,
            total=len(cache_keys),
            succeeded=succeeded,
            failed=failed,
            results=results,
            errors=errors,
        )

    async def multi_set(
        self,
        cache_type: str,
        items: dict[KeyType, Any],
        set_func: Any,
        expire: int | None = None,
    ) -> BatchResult:
        """使用 Pipeline 批量设置缓存数据

        仅在 Redis 模式下使用 Pipeline 优化，其他模式回退到普通批量设置。

        参数:
            cache_type: 缓存类型
            items: 键值对字典
            set_func: 单条设置函数（回退时使用）
            expire: 过期时间（秒）

        返回:
            BatchResult: 批量操作结果
        """
        if not self._check_available():
            return await self._batch_executor.multi_set(
                cache_type, items, set_func, expire
            )

        redis_client = self._backend_mgr.redis_client
        if redis_client is None:
            return await self._batch_executor.multi_set(
                cache_type, items, set_func, expire
            )

        resolved_type = cache_type.upper()
        if not self._registry.is_valid(resolved_type):
            return self._batch_executor.make_disabled_result(
                len(items), "缓存类型未注册"
            )

        results: dict[str, Any] = {}
        errors: dict[str, str] = {}
        succeeded = 0
        failed = 0
        model = self._registry.get_model(resolved_type)
        base_ttl = expire if expire is not None else model.expire
        batch_size = cache_config.pipeline_batch_size
        items_list = list(items.items())
        # 预构建所有 cache_key，避免异常时边界判断
        all_cache_keys = [
            self._registry.build_key(resolved_type, key) for key, _ in items_list
        ]

        for i in range(0, len(items_list), batch_size):
            batch_slice = slice(i, i + batch_size)
            batch_items = items_list[batch_slice]
            batch_keys = all_cache_keys[batch_slice]
            try:
                pipe = redis_client.pipeline(transaction=False)
                ttl = CacheOperations.calc_jitter_ttl(base_ttl)
                for idx, (key, value) in enumerate(batch_items):
                    cache_key = batch_keys[idx]
                    serialized = CacheSerializer.serialize(value)
                    pipe.set(cache_key, serialized, ex=ttl)

                exec_results = await pipe.execute()

                for idx, result in enumerate(exec_results):
                    cache_key = batch_keys[idx]
                    if result:
                        self._registry.add_key(resolved_type, cache_key, base_ttl)
                        results[cache_key] = True
                        succeeded += 1
                    else:
                        errors[cache_key] = "设置失败"
                        failed += 1
            except Exception as e:
                for idx, (key, _) in enumerate(batch_items):
                    cache_key = batch_keys[idx]
                    errors[cache_key] = str(e)
                    failed += 1
                logger.warning("Pipeline批量设置失败", LOG_COMMAND, e=e)

        return BatchResult(
            success=failed == 0,
            total=len(items),
            succeeded=succeeded,
            failed=failed,
            results=results,
            errors=errors,
        )
