"""AI 标签页数据源

直接复用AI插件 config_items 子包的配置项定义，避免硬编码导致的配置残缺。
按配置域分组展示，类型与默认值由 RegisterConfig 元数据自动推断。
"""

from typing import Any

from liuying.configs.utils import RegisterConfig
from liuying.liuying_plugins.AI.config import (
    get_config as get_ai_config,
)
from liuying.liuying_plugins.AI.config import (
    set_config as set_ai_config,
)
from liuying.liuying_plugins.AI.config_items import (
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
    "cast_value",
    "get_config_entry",
    "list_config_entries",
    "update_config_value",
]

# 配置域 -> 中文分组名映射（顺序即为前端展示顺序）
# 贴纸相关配置已归入拟人化分组
_CONFIG_GROUPS: list[tuple[str, list[RegisterConfig]]] = [
    ("基础", MISC_CONFIGS),
    ("LLM模型", LLM_CONFIGS),
    ("Agent", AGENT_CONFIGS),
    ("记忆", MEMORY_CONFIGS),
    ("上下文压缩", CONTEXT_CONFIGS),
    ("拟人化", HUMANIZE_CONFIGS),
    ("TTS语音", TTS_CONFIGS),
    ("视觉多媒体", VISION_CONFIGS),
    ("安全", SAFETY_CONFIGS),
    ("社交主动", SOCIAL_CONFIGS),
]


def _type_name(t: Any) -> str:
    """将Python类型对象转换为前端类型字符串

    参数:
        t: Python类型对象（bool/int/float/str/dict/list等）

    返回:
        str: 类型名字符串
    """
    if t is bool:
        return "bool"
    if t is int:
        return "int"
    if t is float:
        return "float"
    if t is str:
        return "str"
    if t is dict:
        return "dict"
    if t is list:
        return "list"
    return "str"


def _build_registry() -> list[dict[str, Any]]:
    """从AI插件config_items动态构建配置项注册表

    按配置域顺序遍历，遇到重复key时保留首次出现的定义
    （与AI插件config.py的PluginConfig注册顺序一致，MISC先于AGENT/SOCIAL）。
    这样前端不会重复展示同一key，且help文本与首次注册保持一致。

    返回:
        list[dict]: 每项含 key/group/value_type/help/default_value
    """
    registry: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for group_name, configs in _CONFIG_GROUPS:
        if not configs:
            continue
        for cfg in configs:
            upper_key = cfg.key.upper()
            if upper_key in seen_keys:
                continue
            seen_keys.add(upper_key)
            registry.append(
                {
                    "key": cfg.key,
                    "group": group_name,
                    "value_type": _type_name(cfg.type),
                    "help": cfg.help or "",
                    "default_value": cfg.default_value,
                }
            )
    return registry


# 模块加载时一次性构建注册表（配置项在运行时不变）
_REGISTRY: list[dict[str, Any]] = _build_registry()
"""AI插件配置项注册表（由config_items动态生成）"""

_REGISTRY_INDEX: dict[str, dict[str, Any]] = {e["key"]: e for e in _REGISTRY}
"""按key索引的配置项查找表"""


def cast_value(value: Any, value_type: str) -> Any:
    """按类型转换配置值

    参数:
        value: 原始值
        value_type: 目标类型名（bool/int/float/str/dict/list）

    返回:
        Any: 转换后的值

    异常:
        ValueError: 类型转换失败
    """
    if value is None or value == "":
        return None
    if value_type == "bool":
        if isinstance(value, bool):
            return value
        return str(value).lower() in ("true", "1", "yes", "on")
    if value_type == "int":
        return int(value)
    if value_type == "float":
        return float(value)
    if value_type == "dict":
        if isinstance(value, dict):
            return value
        raise ValueError(f"dict类型配置需传入dict，收到: {type(value)}")
    if value_type == "list":
        if isinstance(value, list):
            return value
        raise ValueError(f"list类型配置需传入list，收到: {type(value)}")
    return str(value)


def get_config_entry(key: str) -> dict[str, Any] | None:
    """按key查找配置项定义

    参数:
        key: 配置键名（大写）

    返回:
        dict | None: 配置项定义，未找到返回None
    """
    return _REGISTRY_INDEX.get(key.upper())


def list_config_entries() -> tuple[list[dict[str, Any]], list[str]]:
    """列出全部配置项（含当前值）与分组名

    返回:
        tuple: (配置项列表, 分组名列表)
    """
    entries: list[dict[str, Any]] = []
    groups: list[str] = []
    seen_groups: set[str] = set()
    for item in _REGISTRY:
        key = item["key"]
        raw_value = get_ai_config(key, item["default_value"])
        entries.append(
            {
                "key": key,
                "value": raw_value,
                "value_type": item["value_type"],
                "help_text": item["help"],
                "default_value": item["default_value"],
                "group": item["group"],
            }
        )
        if item["group"] not in seen_groups:
            seen_groups.add(item["group"])
            groups.append(item["group"])
    return entries, groups


def update_config_value(key: str, value: Any) -> dict[str, Any]:
    """更新单个配置项

    参数:
        key: 配置键名
        value: 原始值

    返回:
        dict: 操作结果，含更新后的值

    异常:
        ValueError: key为空或未知或取值非法
    """
    norm_key = str(key).strip().upper()
    if not norm_key:
        raise ValueError("key 不能为空")
    entry = get_config_entry(norm_key)
    if entry is None:
        raise ValueError(f"未知配置项: {norm_key}")
    normalized = cast_value(value, entry["value_type"])
    set_ai_config(norm_key, normalized, auto_save=True)
    return {"ok": True, "key": norm_key, "new_value": normalized}
