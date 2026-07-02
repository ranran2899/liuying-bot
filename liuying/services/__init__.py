"""
LiuYing Bot - 核心服务模块

主要服务包括：
- 数据库 (liuying_db): 提供数据库模型基类和连接管理。
- 缓存 (cache): 提供统一的缓存访问接口。
- 数据访问 (data_access): 提供带缓存的数据访问层。
"""
from nonebot import require

require("nonebot_plugin_alconna")
require("nonebot_plugin_session")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_uninfo")
require("nonebot_plugin_waiter")



from .cache import Cache, CacheDict, CacheList, CacheRoot, cache_config
from .data_access import DataAccess
from .liuying_db import DbUtils, Model, session_manager

__all__ = [
    "Cache",
    "CacheDict",
    "CacheList",
    "CacheRoot",
    "DataAccess",
    "DbUtils",
    "Model",
    "cache_config",
    "session_manager",
]
