"""社交智能子包

提供主动社交门控、配额管理、触发器框架。
"""

from .framework import (
    SocialContext,
    SocialTrigger,
    SocialTriggerRegistry,
    social_trigger_registry,
)
from .gate import SocialGate, social_gate
from .quota import SocialQuota, social_quota

__all__ = [
    "SocialContext",
    "SocialGate",
    "SocialQuota",
    "SocialTrigger",
    "SocialTriggerRegistry",
    "social_gate",
    "social_quota",
    "social_trigger_registry",
]
