"""TTS相关配置项

包含TTS供应商、模型、音色与自动触发等配置。
"""

from ._common import RegisterConfig, cfg

__all__ = ["TTS_CONFIGS"]

TTS_CONFIGS: list[RegisterConfig] = [
    # ===== TTS基础配置 =====
    cfg(
        "TTS",
        {
            "enabled": False,
            "provider": None,
            "model": "tts-1",
            "voice": "alloy",
            "llm_decision_enabled": False,
        },
        "TTS语音配置\n"
        " - enabled: 是否启用\n"
        " - provider: 供应商\n"
        " - model: 模型名\n"
        " - voice: 默认音色\n"
        " - llm_decision_enabled: LLM决策TTS",
        dict,
    ),
    # ===== 自动TTS =====
    cfg(
        "TTS_AUTO",
        {"enabled": False, "probability": 0.2},
        "自动TTS配置\n - enabled: 是否启用\n - probability: 触发概率",
        dict,
    ),
]
"""TTS相关配置项列表"""
