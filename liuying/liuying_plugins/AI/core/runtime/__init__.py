"""运行时层

提供功能开关管理、协议端能力适配、组件组装、
启动引导、外部集成、服务工厂与主动诊断。
"""

from .assembly import RuntimeAssembly, runtime_assembly
from .bootstrap import Bootstrap, bootstrap
from .builder import RuntimeBuilder, runtime_builder
from .diagnostics import Diagnostics, diagnostics
from .factory import ServiceFactory, service_factory
from .integrations import IntegrationManager, integration_manager
from .protocol import Flavor, detect_flavor, emoji_react, poke, set_typing
from .switch import (
    FEATURE_LIST,
    FeatureStatus,
    RuntimeSwitchManager,
    runtime_switch,
)

__all__ = [
    "FEATURE_LIST",
    "Bootstrap",
    "Diagnostics",
    "FeatureStatus",
    "Flavor",
    "IntegrationManager",
    "RuntimeAssembly",
    "RuntimeBuilder",
    "RuntimeSwitchManager",
    "ServiceFactory",
    "bootstrap",
    "detect_flavor",
    "diagnostics",
    "emoji_react",
    "integration_manager",
    "poke",
    "runtime_assembly",
    "runtime_builder",
    "runtime_switch",
    "service_factory",
    "set_typing",
]
