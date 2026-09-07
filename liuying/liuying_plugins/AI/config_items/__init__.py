"""AI插件配置项集合

re-export 各配置域模块的配置项列表，
供 config.py 组装为统一的 PluginConfig。
"""

from .agent_config import AGENT_CONFIGS
from .context_config import CONTEXT_CONFIGS
from .humanize_config import HUMANIZE_CONFIGS
from .llm_config import LLM_CONFIGS
from .memory_config import MEMORY_CONFIGS
from .misc_config import MISC_CONFIGS
from .safety_config import SAFETY_CONFIGS
from .social_config import SOCIAL_CONFIGS
from .tts_config import TTS_CONFIGS
from .vision_config import VISION_CONFIGS

__all__ = [
    "AGENT_CONFIGS",
    "CONTEXT_CONFIGS",
    "HUMANIZE_CONFIGS",
    "LLM_CONFIGS",
    "MEMORY_CONFIGS",
    "MISC_CONFIGS",
    "SAFETY_CONFIGS",
    "SOCIAL_CONFIGS",
    "TTS_CONFIGS",
    "VISION_CONFIGS",
]
