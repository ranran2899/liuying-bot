"""上下文压缩配置项

包含上下文压缩开关与token预算等配置。
"""

from ._common import RegisterConfig, cfg

__all__ = ["CONTEXT_CONFIGS"]

CONTEXT_CONFIGS: list[RegisterConfig] = [
    cfg(
        "CONTEXT_COMPRESS",
        {
            "enabled": True,
            "max_tokens": 2000,
            "keep_recent": 6,
        },
        "上下文压缩配置\n"
        " - enabled: 是否启用\n"
        " - max_tokens: token预算\n"
        " - keep_recent: 保留最近N条",
        dict,
    ),
]
"""上下文压缩配置项列表"""
