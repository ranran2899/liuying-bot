"""安全相关配置项

包含安全过滤与群禁言感知等配置。
"""

from ._common import RegisterConfig, cfg

__all__ = ["SAFETY_CONFIGS"]

SAFETY_CONFIGS: list[RegisterConfig] = [
    cfg(
        "GROUP_MUTE_AWARE",
        True,
        "是否启用群禁言感知",
        bool,
    ),
    cfg(
        "SAFETY_FILTER_ENABLED",
        True,
        "是否启用安全过滤",
        bool,
    ),
]
"""安全相关配置项列表"""
