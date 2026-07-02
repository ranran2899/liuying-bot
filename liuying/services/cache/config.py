"""
缓存系统配置
"""

from enum import StrEnum
from typing import Any, TypeAlias

import nonebot
from pydantic import BaseModel

KeyType: TypeAlias = str | dict[str, Any]
"""缓存键类型，支持字符串或字典参数"""

LOG_COMMAND = "CacheRoot"
"""缓存系统日志标识"""
DEFAULT_EXPIRE = 600
"""默认缓存过期时间（秒）"""
CACHE_KEY_PREFIX = "LIUYING"
"""缓存键前缀"""
CACHE_KEY_SEPARATOR = ":"
"""缓存键分隔符"""
COMPOSITE_KEY_SEPARATOR = "_"
"""复合键分隔符"""
NAMESPACE_SEPARATOR = "@"
"""命名空间分隔符"""
CACHE_TIMEOUT_SECONDS = 3.0
"""缓存操作超时时间（秒）"""
AVALANCHE_JITTER_MAX = 60
"""雪崩防护最大随机偏移量（秒）"""
STAMPEDE_LOCK_TIMEOUT = 10
"""击穿防护互斥锁超时时间（秒）"""
BATCH_CONCURRENCY_LIMIT = 10
"""批量操作默认并发限制"""
DEGRADE_CHECK_INTERVAL = 30
"""降级检测间隔（秒）"""
DEGRADE_MAX_FAILURES = 3
"""降级触发最大连续失败次数"""
CLEANUP_INTERVAL = 60
"""过期数据定时清理间隔（秒）"""
CLEANUP_BATCH_SIZE = 100
"""过期数据每次清理批量大小"""
LOCK_TTL = 30
"""分布式锁默认TTL（秒）"""
LOCK_MAX_AGE = 300
"""锁最大未访问时间（秒）"""
MEMORY_CACHE_MAX_SIZE = 10000
"""内存缓存最大条目数"""
WARMUP_BATCH_SIZE = 100
"""预热批量大小"""
PIPELINE_BATCH_SIZE = 50
"""Pipeline批量大小"""


class CacheMode(StrEnum):
    """缓存模式枚举"""

    MEMORY = "MEMORY"
    """内存缓存 - 使用内存存储缓存数据"""
    REDIS = "REDIS"
    """Redis缓存 - 使用Redis服务器存储缓存数据"""
    NONE = "NONE"
    """不使用缓存 - 将使用ttl=0的内存缓存，相当于直接从数据库获取数据"""


SPECIAL_KEY_FORMATS: dict[str, str] = {
    "LEVEL": "{user_id}" + COMPOSITE_KEY_SEPARATOR + "{group_id}",
    "BAN": "{user_id}" + COMPOSITE_KEY_SEPARATOR + "{group_id}",
    "GROUPS": "{group_id}" + COMPOSITE_KEY_SEPARATOR + "{channel_id}",
}
"""历史遗留的业务键格式映射，新代码应在 register 时显式指定 key_format 覆盖"""


class Config(BaseModel):
    """缓存配置"""

    cache_mode: CacheMode = CacheMode.NONE
    """缓存模式: MEMORY(内存缓存), REDIS(Redis缓存), NONE(不使用缓存)"""
    redis_host: str | None = None
    """redis地址"""
    redis_port: int | None = None
    """redis端口"""
    redis_password: str | None = None
    """redis密码"""
    redis_expire: int = DEFAULT_EXPIRE
    """redis过期时间"""
    avalanche_jitter: int = AVALANCHE_JITTER_MAX
    """雪崩防护随机偏移量（秒），0表示禁用"""
    stampede_lock_timeout: int = STAMPEDE_LOCK_TIMEOUT
    """击穿防护互斥锁超时时间（秒）"""
    batch_concurrency_limit: int = BATCH_CONCURRENCY_LIMIT
    """批量操作并发限制"""
    degrade_check_interval: int = DEGRADE_CHECK_INTERVAL
    """降级检测间隔（秒）"""
    degrade_max_failures: int = DEGRADE_MAX_FAILURES
    """降级触发最大连续失败次数"""
    cleanup_interval: int = CLEANUP_INTERVAL
    """过期数据定时清理间隔（秒），0表示禁用定时清理"""
    cleanup_batch_size: int = CLEANUP_BATCH_SIZE
    """过期数据每次清理批量大小"""
    lock_ttl: int = LOCK_TTL
    """分布式锁TTL（秒）"""
    lock_max_age: int = LOCK_MAX_AGE
    """锁最大未访问时间（秒），超过此时间未访问的锁将被清理"""
    memory_cache_max_size: int = MEMORY_CACHE_MAX_SIZE
    """内存缓存最大条目数，0表示不限制"""
    namespace: str = ""
    """缓存命名空间，用于多租户隔离，为空时不启用命名空间"""
    warmup_batch_size: int = WARMUP_BATCH_SIZE
    """预热批量大小"""
    pipeline_batch_size: int = PIPELINE_BATCH_SIZE
    """Pipeline批量大小，用于Redis批量操作优化"""
    enable_pipeline: bool = True
    """是否启用Pipeline优化"""


class CacheException(Exception):
    """缓存相关异常"""

    def __init__(
        self,
        message: str,
        cache_type: str | None = None,
        key: Any | None = None,
    ):
        """初始化缓存异常

        参数:
            message: 异常信息
            cache_type: 缓存类型（可选）
            key: 缓存键（可选）
        """
        self.message = message
        self.cache_type = cache_type
        self.key = key
        super().__init__(message)

    def __str__(self) -> str:
        """返回异常字符串表示"""
        match (self.cache_type, self.key):
            case (str() as cache_type, str() | dict() as key):
                return f"{self.message} (类型: {cache_type}, 键: {key})"
            case (str() as cache_type, _):
                return f"{self.message} (类型: {cache_type})"
            case _:
                return self.message


cache_config = nonebot.get_plugin_config(Config)
