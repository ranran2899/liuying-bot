"""
缓存系统模块

提供统一的缓存访问接口，支持内存缓存和Redis缓存。

模块结构:
- containers/: 内存容器（CacheDict、CacheList）
- core/: 核心管理逻辑（CacheManager、后端管理、批量操作、降级、锁、注册器、任务）
- config.py: 配置和常量
- models.py: 数据模型
- serializer.py: 序列化器
- monitor.py: 监控统计
- decorators.py: 缓存装饰器
- locks.py: 通用异步锁工具
- cache_class.py: 类型化缓存访问接口

使用示例:
    from liuying.services.cache import Cache, CacheDict, CacheList, CacheRoot

    # 类型化缓存访问
    level_cache = Cache("LEVEL", result_type=list[UserLevel])
    users = await level_cache.get({"user_id": "123", "group_id": "456"})

    # 缓存字典
    config_dict = CacheDict("global_config")
    config_dict["key"] = "value"

    # 缓存列表
    message_list = CacheList("recent_messages")
    message_list.append("新消息")

    # 缓存装饰器
    from liuying.services.cache import cached, cache_evict

    @cached("USER", key_builder=lambda uid: {"user_id": uid})
    async def get_user(user_id: str):
        return await User.get(user_id)

    # 统计信息
    stats = CacheRoot.stats
    monitor = CacheRoot.monitor
"""

import nonebot

from liuying.utils.log import logger

from .cache_class import Cache
from .config import LOG_COMMAND, CacheException, cache_config
from .containers import CacheDict, CacheList
from .core import BatchResult, CacheRoot, WarmupResult
from .decorators import cache_all, cache_evict, cache_put, cached
from .metrics import LatencyStats, MemoryStats
from .monitor import CacheMonitor, monitor_operation

__all__ = [
    "BatchResult",
    "Cache",
    "CacheDict",
    "CacheException",
    "CacheList",
    "CacheMonitor",
    "CacheRoot",
    "LatencyStats",
    "MemoryStats",
    "WarmupResult",
    "cache_all",
    "cache_config",
    "cache_evict",
    "cache_put",
    "cached",
    "monitor_operation",
]

driver = nonebot.get_driver()


@driver.on_startup
async def _on_startup():
    """缓存系统启动"""
    CacheRoot.enabled = True
    await CacheRoot.start_background_tasks()
    logger.info("缓存系统已启用", LOG_COMMAND)


@driver.on_shutdown
async def _on_shutdown():
    """缓存系统关闭"""
    await CacheRoot.close()
