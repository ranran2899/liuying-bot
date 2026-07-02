"""TTS相关配置项

包含TTS供应商、模型、音色与自动触发等配置。
"""

from liuying.configs.utils import RegisterConfig

from ._common import MODULE

__all__ = ["TTS_CONFIGS"]

TTS_CONFIGS: list[RegisterConfig] = [
    RegisterConfig(
        key="TTS_PROVIDER",
        value=None,
        module=MODULE,
        help="TTS语音供应商",
        default_value=None,
        type=str,
    ),
    RegisterConfig(
        key="TTS_MODEL",
        value="tts-1",
        module=MODULE,
        help="TTS模型名",
        default_value="tts-1",
        type=str,
    ),
    RegisterConfig(
        key="TTS_VOICE",
        value="alloy",
        module=MODULE,
        help="默认TTS音色",
        default_value="alloy",
        type=str,
    ),
    RegisterConfig(
        key="TTS_ENABLED",
        value=False,
        module=MODULE,
        help="是否启用TTS",
        default_value=False,
        type=bool,
    ),
    RegisterConfig(
        key="TTS_AUTO_ENABLED",
        value=False,
        module=MODULE,
        help="是否自动TTS",
        default_value=False,
        type=bool,
    ),
    RegisterConfig(
        key="TTS_AUTO_PROBABILITY",
        value=0.2,
        module=MODULE,
        help="自动TTS触发概率",
        default_value=0.2,
        type=float,
    ),
    # ===== Phase8: TTS增强 =====
    RegisterConfig(
        key="TTS_LLM_DECISION_ENABLED",
        value=False,
        module=MODULE,
        help="是否启用LLM决策TTS",
        default_value=False,
        type=bool,
    ),
]
"""TTS相关配置项列表"""
