"""AI WebUI 路由聚合

各路由模块按功能职责拆分，统一在此聚合导出构建函数。
"""

from .acl_routes import build_acl_router
from .config_routes import build_config_router
from .emotion_routes import build_emotion_router
from .group_routes import build_group_router
from .health_routes import build_health_router
from .knowledge_routes import build_knowledge_router
from .memory_routes import build_memory_router
from .persona_routes import build_persona_router
from .runtime_routes import build_runtime_router
from .status_routes import build_status_router
from .token_routes import build_token_router
from .vision_routes import build_vision_router

__all__ = [
    "build_acl_router",
    "build_config_router",
    "build_emotion_router",
    "build_group_router",
    "build_health_router",
    "build_knowledge_router",
    "build_memory_router",
    "build_persona_router",
    "build_runtime_router",
    "build_status_router",
    "build_token_router",
    "build_vision_router",
]
