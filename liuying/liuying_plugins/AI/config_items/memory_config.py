"""记忆相关配置项

包含记忆系统开关、召回、衰减、巩固与历史窗口等配置。
"""

from liuying.configs.utils import RegisterConfig

from ._common import MODULE

__all__ = ["MEMORY_CONFIGS"]

MEMORY_CONFIGS: list[RegisterConfig] = [
    RegisterConfig(
        key="MEMORY_ENABLED",
        value=True,
        module=MODULE,
        help="是否启用记忆系统",
        default_value=True,
        type=bool,
    ),
    RegisterConfig(
        key="MEMORY_RECALL_TOP_K",
        value=5,
        module=MODULE,
        help="记忆召回数量",
        default_value=5,
        type=int,
    ),
    RegisterConfig(
        key="MEMORY_RECALL_MODE",
        value="auto",
        module=MODULE,
        help="记忆召回模式：auto/fast/deep",
        default_value="auto",
        type=str,
    ),
    RegisterConfig(
        key="MEMORY_DECAY_ENABLED",
        value=True,
        module=MODULE,
        help="是否启用记忆衰减",
        default_value=True,
        type=bool,
    ),
    RegisterConfig(
        key="MEMORY_CONSOLIDATION_ENABLED",
        value=True,
        module=MODULE,
        help="是否启用记忆巩固",
        default_value=True,
        type=bool,
    ),
    RegisterConfig(
        key="HISTORY_LEN",
        value=20,
        module=MODULE,
        help="历史对话窗口长度",
        default_value=20,
        type=int,
    ),
]
"""记忆相关配置项列表"""
