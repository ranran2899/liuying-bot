"""社交智能子包

提供主动社交配额管理与触发器框架。
主动发言门控已迁移至 agent.review.social_gate，
需要时直接从该模块导入。
"""

from .framework import (
    SocialContext,
    SocialTrigger,
    SocialTriggerRegistry,
    social_trigger_registry,
)
from .quota import SocialQuota, social_quota

__all__ = [
    "SocialContext",
    "SocialQuota",
    "SocialTrigger",
    "SocialTriggerRegistry",
    "social_quota",
    "social_trigger_registry",
]
