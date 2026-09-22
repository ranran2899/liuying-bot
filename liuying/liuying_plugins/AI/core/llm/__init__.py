"""LLM 调用基础层

封装 LLM 调用、供应商路由、token 记账、
模型按角色路由与多CLI路由降级。
"""

from .ai_routes import AiCliRoute, AiCliRouter, ai_cli_router
from .helper import LLMHelper, llm_helper
from .model_router import (
    ModelCapability,
    ModelRole,
    ModelRouter,
    declared_capabilities,
    model_router,
)
from .provider_router import ProviderRouter, ProviderState, provider_router
from .token_ledger import (
    TokenLedger,
    TokenTrackingHelper,
    token_ledger,
)

__all__ = [
    "AiCliRoute",
    "AiCliRouter",
    "LLMHelper",
    "ModelCapability",
    "ModelRole",
    "ModelRouter",
    "ProviderRouter",
    "ProviderState",
    "TokenLedger",
    "TokenTrackingHelper",
    "ai_cli_router",
    "declared_capabilities",
    "llm_helper",
    "model_router",
    "provider_router",
    "token_ledger",
]
