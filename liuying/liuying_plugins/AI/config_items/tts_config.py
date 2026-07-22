"""TTS相关配置项

包含TTS供应商、模型、音色与自动触发等配置。
采用嵌套字典组织相关配置项，提升可读性。
"""

from liuying.configs.utils import RegisterConfig

from ._common import MODULE

__all__ = ["TTS_CONFIGS"]

TTS_CONFIGS: list[RegisterConfig] = [
    # ===== TTS基础配置 =====
    RegisterConfig(
        key="TTS",
        value={
            "enabled": False,
            "provider": None,
            "model": "tts-1",
            "voice": "alloy",
            "llm_decision_enabled": False,
        },
        module=MODULE,
        help=(
            "TTS语音配置\n"
            " - enabled: 是否启用\n"
            " - provider: 供应商\n"
            " - model: 模型名\n"
            " - voice: 默认音色\n"
            " - llm_decision_enabled: LLM决策TTS"
        ),
        default_value={
            "enabled": False,
            "provider": None,
            "model": "tts-1",
            "voice": "alloy",
            "llm_decision_enabled": False,
        },
        type=dict,
    ),
    # ===== 自动TTS =====
    RegisterConfig(
        key="TTS_AUTO",
        value={
            "enabled": False,
            "probability": 0.2,
        },
        module=MODULE,
        help=(
            "自动TTS配置\n"
            " - enabled: 是否启用\n"
            " - probability: 触发概率"
        ),
        default_value={"enabled": False, "probability": 0.2},
        type=dict,
    ),
]
"""TTS相关配置项列表"""
