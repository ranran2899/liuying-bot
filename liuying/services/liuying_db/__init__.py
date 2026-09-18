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


@PriorityLifecycle.on_shutdown(priority=1)
async def shutdown():
    """数据库关闭入口，由 NoneBot 关闭钩子调用

    关闭钩子按优先级降序执行，priority=1 使数据库在全部业务服务
    （含聊天记录/统计/行为日志队列的关停刷库）完成清理后最后断开。
    先停止同步任务，再释放全部数据库连接。
    """
    await sync_manager.stop_sync()
    await session_manager.disconnect()


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
