"""数据库服务模块

统一的数据库服务入口，通过 re-export 暴露公共 API:
- 模型基类: ``Model``、``Base``
- 查询构建: ``QueryWrapper``、``Q``、``build_filter_statement``
- 会话管理: ``session_manager`` 单例、``nested_transaction``
- 同步能力: ``sync_manager`` 单例
- 工具集合: ``DbUtils``（``with_db_timeout``、``get_column`` 等）
- 异常类: ``DbConnectError``、``DbUrlIsNone``
"""
from liuying.utils.manager.priority_manager import PriorityLifecycle

from .base_model import Base, Model
from .exceptions import DbConnectError, DbUrlIsNone
from .lifecycle import LifecycleManager
from .query import Q, QueryWrapper, build_filter_statement
from .session import nested_transaction, session_manager
from .sync import sync_manager
from .utils import DbUtils


@PriorityLifecycle.on_startup(priority=1)
async def init():
    """数据库初始化入口，由 NoneBot 启动钩子调用

    委托 ``LifecycleManager.initialize`` 执行完整初始化流程。
    """
    await LifecycleManager.initialize()


__all__ = [
    "Base",
    "DbConnectError",
    "DbUrlIsNone",
    "DbUtils",
    "Model",
    "Q",
    "QueryWrapper",
    "build_filter_statement",
    "nested_transaction",
    "session_manager",
    "sync_manager",
]
