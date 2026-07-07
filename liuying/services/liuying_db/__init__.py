"""数据库服务模块

统一的数据库服务入口，通过 re-export 暴露公共 API：
- 模型基类：``Model``、``Base``
- 会话管理：``session_manager`` 单例、``DatabaseSessionManager``、``nested_transaction``
- 连接工厂：``connection_registry`` 单例、``ConnectionRegistry``
- 生命周期：``init``（启动时自动触发）、``LifecycleManager``
- 同步能力：``sync_manager`` 单例、``DBSyncManager``
- 工具集合：``DbUtils``（``with_db_timeout``、``get_column`` 等）
- 配置常量：``DB_TIMEOUT_SECONDS``、``SLOW_QUERY_THRESHOLD``、``db_model``
- 异常类：``DbConnectError``、``DbUrlIsNone``
"""
from liuying.utils.manager.priority_manager import PriorityLifecycle

from .base_model import Base, Model
from .config import (
    DB_TIMEOUT_SECONDS,
    SLOW_QUERY_THRESHOLD,
    db_model,
)
from .connection_registry import ConnectionRegistry, connection_registry
from .exceptions import DbConnectError, DbUrlIsNone
from .lifecycle import LifecycleManager
from .session import DatabaseSessionManager, nested_transaction, session_manager
from .sync import DBSyncManager, sync_manager
from .utils import DbUtils


@PriorityLifecycle.on_startup(priority=1)
async def init():
    """数据库初始化入口，由 NoneBot 启动钩子调用

    委托 ``LifecycleManager.initialize`` 执行完整初始化流程。
    """
    await LifecycleManager.initialize()


__all__ = [
    "DB_TIMEOUT_SECONDS",
    "SLOW_QUERY_THRESHOLD",
    "Base",
    "ConnectionRegistry",
    "DBSyncManager",
    "DatabaseSessionManager",
    "DbConnectError",
    "DbUrlIsNone",
    "DbUtils",
    "LifecycleManager",
    "Model",
    "connection_registry",
    "db_model",
    "nested_transaction",
    "session_manager",
    "sync_manager",
]
