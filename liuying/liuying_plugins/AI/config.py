"""流萤AI插件配置模块

定义注册到 plugins2config.yaml 的配置项列表，
以及统一的配置读取封装 get_config（直接对接流萤配置系统 ConfigsManager）。

配置项按域拆分至 config_items 子包，本模块仅负责组装与读写封装。
"""

from typing import Any

from liuying.configs.config import Config as ConfigManager
from liuying.configs.utils import RegisterConfig

from .config_items import (
    AGENT_CONFIGS,
    CONTEXT_CONFIGS,
    HUMANIZE_CONFIGS,
    LLM_CONFIGS,
    MEMORY_CONFIGS,
    MISC_CONFIGS,
    POKE_CONFIGS,
    SAFETY_CONFIGS,
    SOCIAL_CONFIGS,
    TTS_CONFIGS,
    VISION_CONFIGS,
)

__all__ = ["PluginConfig", "get_config", "set_config"]

_MODULE = "AI"
"""配置模块名"""


PluginConfig: list[RegisterConfig] = [
    *    MISC_CONFIGS,
    *POKE_CONFIGS,
    *LLM_CONFIGS,
    *TTS_CONFIGS,
    *VISION_CONFIGS,
    *AGENT_CONFIGS,
    *MEMORY_CONFIGS,
    *HUMANIZE_CONFIGS,
    *SAFETY_CONFIGS,
    *SOCIAL_CONFIGS,
    *CONTEXT_CONFIGS,
]
"""流萤AI插件配置项列表（注册到 plugins2config.yaml 的 AI 模块）"""


def get_config(key: str, default: Any = None) -> Any:
    """读取AI插件配置值

    直接对接流萤配置系统 ConfigsManager，支持自动类型转换与默认值。

    参数:
        key: 配置键名（大小写不敏感，内部会upper）
        default: 默认值

    返回:
        Any: 配置值，未找到时返回默认值
    """
    return ConfigManager.get_config(_MODULE, key, default)


def set_config(
    key: str, value: Any, auto_save: bool = True
) -> None:
    """写入AI插件配置值

    对接流萤配置系统 ConfigsManager.set_config。

    参数:
        key: 配置键名（大小写不敏感，内部会upper）
        value: 配置值
        auto_save: 是否立即持久化到文件
    """
    ConfigManager.set_config(
        _MODULE, key, value, auto_save=auto_save
    )
