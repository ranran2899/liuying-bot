"""AI运行时开关管理器

开关唯一事实源为配置系统：读取走插件 config.get_config（5秒TTL
缓存削减热路径开销），写入统一经 config.set_config（即时清理缓存），
不再维护独立内存状态，消除旧版内存态与配置双轨漂移。

功能列表 FEATURE_LIST 与配置键映射 _CONFIG_KEY_MAP 同源生成，
避免二者漂移导致开关 advertised 却无法持久化/生效。
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import TypedDict

from liuying.utils.log import logger

from ...config import get_config, set_config

__all__ = [
    "FEATURE_LIST",
    "Feature",
    "FeatureStatus",
    "RuntimeSwitchManager",
    "runtime_switch",
]


class Feature(StrEnum):
    """受运行时开关管理的子功能枚举

    成员即 str，与配置键映射、admin 传入的功能名完全兼容。
    """

    AI = "ai"
    AGENT = "agent"
    MEMORY = "memory"
    VISION = "vision"
    TTS = "tts"
    STICKER = "sticker"
    PROACTIVE = "proactive"
    SOCIAL_INTELLIGENCE = "social_intelligence"
    DIARY = "diary"
    WEBUI = "webui"
    SAFETY_FILTER = "safety_filter"


_CONFIG_KEY_MAP: dict[str, tuple[str, str | None]] = {
    Feature.AI: ("ENABLE_AI", None),
    Feature.AGENT: ("AGENT", "enabled"),
    Feature.MEMORY: ("MEMORY_ENABLED", None),
    Feature.VISION: ("VISION", "enabled"),
    Feature.TTS: ("TTS", "enabled"),
    Feature.STICKER: ("STICKER", "enabled"),
    Feature.PROACTIVE: ("PROACTIVE", "enabled"),
    Feature.SOCIAL_INTELLIGENCE: ("SOCIAL_INTELLIGENCE_ENABLED", None),
    Feature.DIARY: ("DIARY_ENABLED", None),
    Feature.WEBUI: ("WEBUI_ENABLED", None),
    Feature.SAFETY_FILTER: ("SAFETY_FILTER_ENABLED", None),
}
"""功能名到配置键的映射（用于读写配置）

值为 (config_key, sub_key) 元组：
- sub_key 为 None 时直接读写 config_key
- sub_key 不为 None 时读写 config_key 配置组下的 sub_key 子键
"""


FEATURE_LIST: tuple[str, ...] = tuple(_CONFIG_KEY_MAP)
"""受运行时开关管理的子功能名列表（与配置键映射同源，避免漂移）"""


def _config_key_str(feature: str) -> str:
    """获取功能对应的配置键字符串表示

    参数:
        feature: 功能名

    返回:
        str: 配置键字符串，嵌套键格式为 "GROUP.sub_key"
    """
    mapping = _CONFIG_KEY_MAP.get(feature)
    if not mapping:
        return ""
    config_key, sub_key = mapping
    return f"{config_key}.{sub_key}" if sub_key else config_key


@dataclass(slots=True)
class FeatureStatus:
    """功能状态

    Attributes:
        name: 功能名
        enabled: 是否启用
        config_key: 对应的配置键，无则空串
    """

    name: str
    enabled: bool
    config_key: str = ""


class FeatureState(TypedDict):
    """单个功能的健康状态快照"""

    name: str
    enabled: bool
    config_key: str


class SwitchHealth(TypedDict):
    """运行时开关体检报告"""

    total_features: int
    enabled_count: int
    disabled_count: int
    disabled_features: list[str]
    features: list[FeatureState]


class RuntimeSwitchManager:
    """运行时开关管理器

    管理AI插件总开关与子功能的全局开关，读写均直达配置系统；
    各功能门禁既可直接读本开关（推荐，经映射避免键名漂移），
    也可继续读对应配置键（同一数据源，无一致性问题）。
    """

    def is_enabled(self, feature: str) -> bool:
        """查询功能是否启用（直接读配置，全局维度）

        无映射的功能名默认视为启用，保持历史行为。

        参数:
            feature: 功能名

        返回:
            bool: 是否启用
        """
        mapping = _CONFIG_KEY_MAP.get(feature)
        if not mapping:
            return True
        config_key, sub_key = mapping
        if sub_key is None:
            return bool(get_config(config_key, True))
        config_group = get_config(config_key, {})
        if not isinstance(config_group, dict):
            return True
        return bool(config_group.get(sub_key, True))

    def set_global(self, feature: str, enabled: bool) -> bool:
        """设置全局开关并持久化

        经插件 config.set_config 写入，即时清理读取缓存，
        所有门禁读取方（含直接使用 get_config 的功能键）
        下一次读取即可拿到新值。

        参数:
            feature: 功能名
            enabled: 是否启用

        返回:
            bool: 是否成功（功能名无映射时失败）
        """
        if feature not in FEATURE_LIST:
            return False
        config_key, sub_key = _CONFIG_KEY_MAP[feature]
        if sub_key is None:
            set_config(config_key, enabled)
        else:
            config_group = get_config(config_key, {})
            if not isinstance(config_group, dict):
                config_group = {}
            config_group[sub_key] = enabled
            set_config(config_key, config_group)
        logger.info(
            f"全局开关 {feature}={enabled}",
            command="AI",
        )
        return True

    def get_status(self) -> list[FeatureStatus]:
        """获取所有功能的全局状态

        返回:
            list[FeatureStatus]: 功能状态列表
        """
        return [
            FeatureStatus(
                name=feature,
                enabled=self.is_enabled(feature),
                config_key=_config_key_str(feature),
            )
            for feature in FEATURE_LIST
        ]

    def health_check(self) -> SwitchHealth:
        """功能体检：返回所有功能状态与计数

        返回:
            dict: 体检报告
        """
        statuses = self.get_status()
        enabled_count = sum(1 for s in statuses if s.enabled)
        disabled_features = [
            s.name for s in statuses if not s.enabled
        ]
        return {
            "total_features": len(statuses),
            "enabled_count": enabled_count,
            "disabled_count": len(statuses) - enabled_count,
            "disabled_features": disabled_features,
            "features": [
                {
                    "name": s.name,
                    "enabled": s.enabled,
                    "config_key": s.config_key,
                }
                for s in statuses
            ],
        }


runtime_switch = RuntimeSwitchManager()
"""运行时开关管理器单例"""
