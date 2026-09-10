"""运行时层

提供功能开关管理与协议端能力适配。
"""

from .protocol import Flavor, ProtocolHelper
from .switch import (
    FEATURE_LIST,
    FeatureStatus,
    RuntimeSwitchManager,
    runtime_switch,
)

__all__ = [
    "FEATURE_LIST",
    "FeatureStatus",
    "Flavor",
    "ProtocolHelper",
    "RuntimeSwitchManager",
    "runtime_switch",
]
