"""缓存配置读取"""

from liuying.configs.config import Config


def get_cache_conf() -> tuple[bool, int]:
    """读取会话缓存配置

    返回:
        (是否启用缓存, 缓存过期秒数)
    """
    enabled = bool(Config.get_config("platform_session", "CACHE", True))
    expire = int(Config.get_config("platform_session", "CACHE_EXPIRE", 300))
    return enabled, expire
