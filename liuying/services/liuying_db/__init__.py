"""数据库服务模块

统一的数据库服务入口，通过 re-export 暴露公共 API：
- 模型基类：``Model``、``Base``
- 会话管理：``session_manager`` 单例（``get_session``、``disconnect`` 等）
- 事务工具：``nested_transaction``
- 连接工厂：``connection_registry`` 单例（``create_engine``、``register`` 等）
- 生命周期：``init``（启动时自动触发）、``LifecycleManager``
- 搜索能力：``SearchManager``、``search_manager``、``init_search_tables``
- 同步能力：``sync_manager`` 单例
- 工具集合：``DbUtils``（``with_db_timeout``、``get_column`` 等）
- 配置常量：``DB_TIMEOUT_SECONDS``、``SLOW_QUERY_THRESHOLD``、``db_model``

业务逻辑分布在子模块中：
- ``config``: 配置常量与 ``get_config``
- ``base_model``: ORM 增删改查基类
- ``session``: 会话管理器 ``SessionManager`` 与单例 ``session_manager``
- ``connection_registry``: 连接工厂注册中心 ``ConnectionRegistry``
- ``lifecycle``: 生命周期管理器 ``LifecycleManager`` 与启动钩子 ``init``
- ``sync``: 主从同步管理器 ``DBSyncManager``
- ``query``: 查询构建器
- ``search``: 全文检索与向量存储
- ``monitoring``: 连接池与泄漏监控
"""
from liuying.utils.manager.priority_manager import PriorityLifecycle

from .base_model import Base, Model
# from .config import DB_TIMEOUT_SECONDS, SLOW_QUERY_THRESHOLD, db_model
from .connection_registry import ConnectionRegistry, connection_registry
# from .exceptions import DbConnectError, DbUrlIsNone
from .lifecycle import LifecycleManager
from .search import SearchManager, init_search_tables, search_manager
from .session import session_manager

# from .sync import DBSyncManager, sync_manager
from .utils import DbUtils

# MODELS = db_model.models

@PriorityLifecycle.on_startup(priority=1)
async def init():
    """数据库初始化入口，由 NoneBot 启动钩子调用

    委托 ``LifecycleManager.initialize`` 执行完整初始化流程。
    """
    await LifecycleManager.initialize()



__all__ = [
    "Base",
    "Model",
    "ConnectionRegistry",
    "connection_registry",
    "SearchManager",
    "init_search_tables",
    "search_manager",
    "session_manager",

    "DbUtils",
]
