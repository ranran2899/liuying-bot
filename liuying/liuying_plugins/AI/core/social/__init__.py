"""社交智能子包

提供主动社交门控、配额管理、触发器框架。
"""

from .framework import (
    SocialContext,
    SocialTrigger,
    list_social_triggers,
    register_social_trigger,
)
from .gate import SocialGate, social_gate
from .quota import SocialQuota, social_quota

__all__ = [
    "SocialContext",
    "SocialGate",
    "SocialQuota",
    "SocialTrigger",
    "list_social_triggers",
    "register_social_trigger",
    "social_gate",
    "social_quota",
]
