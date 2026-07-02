"""缓存初始化模块

负责注册各种缓存类型，实现按需缓存机制
"""

from liuying.models._user.user_info import UserInfo
from liuying.models.ban_console import BanConsole
from liuying.models._bot import BotConsole
from liuying.models._group import GroupConsole
from liuying.models._user import UserLevel
from liuying.models.plugin_info import PluginInfo
from liuying.models.sensitive_word import SensitiveWord
from liuying.models._bot.qq_bot_config import QQBotConfig
from liuying.services.cache import CacheRoot, cache_config
from liuying.services.cache.config import CacheMode
from liuying.utils.enum import CacheType
from liuying.utils.log import logger


def register_cache_types() -> None:
    """注册所有缓存类型"""
    cache_registrations = [
        (CacheType.PLUGINS, PluginInfo, None),
        (CacheType.USERS, UserInfo, None),
        (CacheType.GROUPS, GroupConsole, None),
        (CacheType.BOT, BotConsole, None),
        (CacheType.LEVEL, UserLevel, "{user_id}_{group_id}_{bot_id}"),
        (CacheType.BAN, BanConsole, "{user_id}_{group_id}"),
        (CacheType.SENSITIVE, list[SensitiveWord], None),
        (
            CacheType.QQ_BOT_CONFIG,
            QQBotConfig,
            "{user_id}_{bot_id}",
        ),
    ]

    for cache_type, model, key_format in cache_registrations:
        kwargs = {"key_format": key_format} if key_format else {}
        CacheRoot.register(cache_type, model, **kwargs)

    if cache_config.cache_mode == CacheMode.NONE:
        logger.info("缓存功能已禁用，将直接从数据库获取数据")
    else:
        logger.info(f"已注册所有缓存类型，缓存模式: {cache_config.cache_mode}")
        logger.info("使用增量缓存模式，数据将按需加载到缓存中")
