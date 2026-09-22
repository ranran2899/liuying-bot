"""流萤AI插件配置模块

定义注册到 plugins2config.yaml 的配置项列表，
以及统一的配置读取封装 get_config（直接对接流萤配置系统 ConfigsManager）。

配置项按域拆分至 config_items 子包，本模块仅负责组装与读写封装。
get_config 带 5 秒 TTL 缓存，削减热路径（runner 每轮读 AGENT 等）
重复的类型转换与模型构建开销。
"""

import copy
import time
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
    SAFETY_CONFIGS,
    SOCIAL_CONFIGS,
    TTS_CONFIGS,
    VISION_CONFIGS,
)

__all__ = [
    "DEFAULT_PERSONA_FALLBACK",
    "PluginConfig",
    "get_config",
    "set_config",
]

_MODULE = "AI"
"""配置模块名"""

DEFAULT_PERSONA_FALLBACK = "default"
"""数据列默认人格名（人格/记忆/情绪等表未声明人格时的占位值）

注意与运行默认人格区分：实际服务的人格由 DEFAULT_PERSONA
配置决定（默认 liuying），两者语义不同不可混用。"""

_CACHE: dict[tuple[str, str], tuple[float, object]] = {}
"""配置读取 TTL 缓存 {(模块, 键): (过期单调时间戳, 配置值)}"""

_CACHE_TTL = 5.0
"""缓存生存时间（秒）

兼顾热路径读开销与配置热改生效时延：set_config 主动清缓存
保证写入方即时生效，绕过本封装的写入（如运行时开关直接调
ConfigManager.set_config）最多延迟本 TTL 后可见。
"""


def get_config(key: str, default: Any = None) -> Any:
    """读取AI插件配置值

    直接对接流萤配置系统 ConfigsManager，支持自动类型转换与默认值。

    带 TTL 缓存：命中且未过期直接返回（dict/list 返回浅拷贝，
    防止调用方就地修改污染缓存）；配置缺失（返回值即默认值）
    时不缓存，保证不同默认值的调用各自正确。

    参数:
        key: 配置键名（大小写不敏感，内部会upper）
        default: 默认值

    返回:
        Any: 配置值，未找到时返回默认值
    """
    cache_key = (_MODULE, key.upper())
    now = time.monotonic()
    hit = _CACHE.get(cache_key)
    if hit is not None and hit[0] > now:
        value = hit[1]
    else:
        value = ConfigManager.get_config(_MODULE, key, default)
        # 仅缓存真实配置值：缺失时返回值即默认值本身，
        # 缓存会导致不同默认值的调用互相污染
        if value is not default:
            _CACHE[cache_key] = (now + _CACHE_TTL, value)
    if isinstance(value, (dict, list)):
        return copy.copy(value)
    return value


def set_config(
    key: str, value: Any, auto_save: bool = True
) -> None:
    """写入AI插件配置值

    对接流萤配置系统 ConfigsManager.set_config，
    写入后清空 TTL 缓存保证后续读取即时拿到新值。

    参数:
        key: 配置键名（大小写不敏感，内部会upper）
        value: 配置值
        auto_save: 是否立即持久化到文件
    """
    ConfigManager.set_config(
        _MODULE, key, value, auto_save=auto_save
    )
    # 清空整个缓存而非单键：模块内键数量有限，全清代价可忽略，
    # 且能覆盖嵌套配置组更新（改组内子键）导致的连带失效
    _CACHE.clear()


PluginConfig: list[RegisterConfig] = [
    *MISC_CONFIGS,
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
