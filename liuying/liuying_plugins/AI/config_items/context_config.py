"""上下文压缩配置项

包含上下文压缩开关与token预算等配置。
采用嵌套字典组织相关配置项，提升可读性。
"""

from liuying.configs.utils import RegisterConfig

from ._common import MODULE

__all__ = ["CONTEXT_CONFIGS"]

CONTEXT_CONFIGS: list[RegisterConfig] = [
    RegisterConfig(
        key="CONTEXT_COMPRESS",
        value={
            "enabled": True,
            "max_tokens": 2000,
            "keep_recent": 6,
        },
        module=MODULE,
        help=(
            "上下文压缩配置\n"
            " - enabled: 是否启用\n"
            " - max_tokens: token预算\n"
            " - keep_recent: 保留最近N条"
        ),
        default_value={
            "enabled": True,
            "max_tokens": 2000,
            "keep_recent": 6,
        },
        type=dict,
    ),
]
"""上下文压缩配置项列表"""
