"""AI 标签页路由聚合

将流萤AI插件的管理能力（状态/配置/运行时/记忆/人格/视觉/知识库/Token/权限）
整合为统一路由器，挂载到流萤本体WebUI的 /liuying/api/ai/* 前缀下。

统一使用流萤本体WebUI的JWT认证体系（authentication依赖），
不再依赖原独立插件的超级用户query参数鉴权。
"""

from fastapi import APIRouter

from .config_routes import router as config_router
from .extra_routes import router as extra_router
from .memory_routes import router as memory_router
from .persona_routes import router as persona_router
from .runtime_routes import router as runtime_router
from .status_routes import router as status_router

__all__ = ["router"]

# 主路由器不设置prefix，各子路由自带完整prefix（如 /ai、/ai/config、/ai/runtime）
# 避免 status_router 的 prefix 与子路由 prefix 叠加导致路径重复
# （如 /ai + /ai/config = /ai/ai/config 的错误路径）
router = APIRouter()
"""AI标签页主路由器（聚合所有子路由，自身不设置prefix）"""

# 聚合各功能子路由（各子路由已有完整的prefix定义）
router.include_router(status_router)
router.include_router(config_router)
router.include_router(runtime_router)
router.include_router(memory_router)
router.include_router(persona_router)
router.include_router(extra_router)
