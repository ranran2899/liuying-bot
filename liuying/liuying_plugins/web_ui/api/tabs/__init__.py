from .database import router as database_router
from .main import router as main_router
from .manage import router as manage_router
from .plugin_manage import router as plugin_router
from .system import router as system_router

__all__ = [
    "database_router",
    "main_router",
    "manage_router",
    "plugin_router",
    "system_router",
]
