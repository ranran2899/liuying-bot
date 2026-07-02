"""上下文压缩配置项

包含上下文压缩开关与token预算等配置。
"""

from liuying.configs.utils import RegisterConfig

from ._common import MODULE

__all__ = ["CONTEXT_CONFIGS"]

CONTEXT_CONFIGS: list[RegisterConfig] = [
    RegisterConfig(
        key="CONTEXT_COMPRESS_ENABLED",
        value=True,
        module=MODULE,
        help="是否启用上下文压缩",
        default_value=True,
        type=bool,
    ),
    RegisterConfig(
        key="CONTEXT_MAX_TOKENS",
        value=2000,
        module=MODULE,
        help="上下文压缩token预算",
        default_value=2000,
        type=int,
    ),
    RegisterConfig(
        key="CONTEXT_KEEP_RECENT",
        value=6,
        module=MODULE,
        help="上下文压缩保留最近N条",
        default_value=6,
        type=int,
    ),
]
"""上下文压缩配置项列表"""
