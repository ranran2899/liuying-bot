"""运行时层

提供功能开关管理、协议端能力适配与主动诊断。
"""

from .diagnostics import Diagnostics, diagnostics
from .protocol import Flavor, ProtocolHelper
from .switch import (
    FEATURE_LIST,
    FeatureStatus,
    RuntimeSwitchManager,
    runtime_switch,
)

__all__ = [
    "FEATURE_LIST",
    "Diagnostics",
    "FeatureStatus",
    "Flavor",
    "ProtocolHelper",
    "RuntimeSwitchManager",
    "diagnostics",
    "runtime_switch",
]
