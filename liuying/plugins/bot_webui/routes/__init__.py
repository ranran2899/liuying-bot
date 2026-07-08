"""本体 WebUI 路由聚合

各路由模块按功能职责拆分，统一在此聚合导出构建函数。
"""

from .bot_routes import build_bot_router
from .group_routes import build_group_router
from .health_routes import build_health_router
from .log_routes import build_log_router
from .plugin_routes import build_plugin_router
from .stats_routes import build_stats_router
from .status_routes import build_status_router
from .system_routes import build_system_router
from .task_routes import build_task_router

__all__ = [
    "build_bot_router",
    "build_group_router",
    "build_health_router",
    "build_log_router",
    "build_plugin_router",
    "build_stats_router",
    "build_status_router",
    "build_system_router",
    "build_task_router",
]
