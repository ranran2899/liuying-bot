"""拍一拍响应配置项

响应群内戳一戳事件的相关配置。
"""

from liuying.configs.utils import RegisterConfig

from ._common import MODULE

__all__ = ["POKE_CONFIGS"]

POKE_CONFIGS: list[RegisterConfig] = [
    RegisterConfig(
        key="POKE",
        value={"enabled": True, "probability": 0.3},
        module=MODULE,
        help=(
            "拍一拍响应配置\n"
            " - enabled: 是否启用戳回\n"
            " - probability: 戳回概率（0-1）"
        ),
        default_value={"enabled": True, "probability": 0.3},
        type=dict,
    ),
]
