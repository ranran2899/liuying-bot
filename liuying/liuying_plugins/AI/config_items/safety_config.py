"""安全相关配置项

包含安全过滤、群禁言感知与内容审核等配置。
"""

from liuying.configs.utils import RegisterConfig

from ._common import MODULE

__all__ = ["SAFETY_CONFIGS"]

SAFETY_CONFIGS: list[RegisterConfig] = [
    RegisterConfig(
        key="GROUP_MUTE_AWARE",
        value=True,
        module=MODULE,
        help="是否启用群禁言感知",
        default_value=True,
        type=bool,
    ),
    RegisterConfig(
        key="SAFETY_FILTER_ENABLED",
        value=True,
        module=MODULE,
        help="是否启用安全过滤",
        default_value=True,
        type=bool,
    ),
    RegisterConfig(
        key="CONTENT_MODERATION_ENABLED",
        value=True,
        module=MODULE,
        help="是否启用内容审核",
        default_value=True,
        type=bool,
    ),
]
"""安全相关配置项列表"""
