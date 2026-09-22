"""AI运行时开关管理器

提供内存级全局开关 + 配置文件持久化（通过 ConfigManager.set_config）。

设计说明：仅保留全局维度的功能开关。旧版的群组级/用户级 override 覆盖
在执行链路中从未被真正读取（除总开关 ai 外，各功能门禁均直接读 config，
如 get_config("MEMORY_ENABLED")），因此 set_group/set_user 写入的内存覆盖
静默失效。按"全局开关写回配置、各门禁按 config 生效"的单一模型，已移除
群组/用户级覆盖 machinery。

功能列表 FEATURE_LIST 与配置键映射 _CONFIG_KEY_MAP 同源生成，
避免二者漂移导致开关 advertised 却无法持久化/生效。
"""

from dataclasses import dataclass
from enum import StrEnum
import threading
from typing import TypedDict

from liuying.configs.config import Config as ConfigManager
from liuying.utils.log import logger

from ...config import get_config

__all__ = [
    "FEATURE_LIST",
    "Feature",
    "FeatureStatus",
    "RuntimeSwitchManager",
    "runtime_switch",
]

_MODULE = "AI"
"""配置模块名"""


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
"""功能名到配置键的映射（用于读写配置文件）

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

    管理AI插件总开关与子功能的全局开关。全局状态从配置文件加载，
    运行时修改可持久化回配置文件；各功能门禁按 config 生效。
    """

    def __init__(self) -> None:
        """初始化运行时开关管理器"""
        self._global_state: dict[str, bool] = {}
        """全局开关状态"""
        self._lock = threading.RLock()
        """并发锁"""
        self._initialized = False
        """是否已初始化"""

    def initialize(self) -> None:
        """从配置文件加载全局开关状态"""
        with self._lock:
            if self._initialized:
                return
            self._global_state = {
                feature: self._load_from_config(feature)
                for feature in FEATURE_LIST
            }
            self._initialized = True
            logger.debug(
                f"运行时开关初始化完成: {len(self._global_state)} 项",
                command="AI",
            )

    def _load_from_config(self, feature: str) -> bool:
        """从配置加载功能开关

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
            value = get_config(config_key, True)
        else:
            config_group = get_config(config_key, {})
            value = (
                config_group.get(sub_key, True)
                if isinstance(config_group, dict)
                else True
            )
        return bool(value)

    def _save_to_config(self, feature: str, enabled: bool) -> bool:
        """持久化功能开关到配置文件

        参数:
            feature: 功能名
            enabled: 是否启用

        返回:
            bool: 是否成功持久化
        """
        mapping = _CONFIG_KEY_MAP.get(feature)
        if not mapping:
            return False
        config_key, sub_key = mapping
        if sub_key is None:
            ConfigManager.set_config(_MODULE, config_key, enabled)
        else:
            config_group = get_config(config_key, {})
            if not isinstance(config_group, dict):
                config_group = {}
            config_group[sub_key] = enabled
            ConfigManager.set_config(
                _MODULE, config_key, config_group
            )
        return True

    def is_enabled(self, feature: str) -> bool:
        """查询功能是否启用（全局维度）

        参数:
            feature: 功能名

        返回:
            bool: 是否启用
        """
        with self._lock:
            if not self._initialized:
                self.initialize()
            return self._global_state.get(feature, True)

    def set_global(
        self, feature: str, enabled: bool, *, persist: bool = True
    ) -> bool:
        """设置全局开关

        参数:
            feature: 功能名
            enabled: 是否启用
            persist: 是否持久化到配置文件

        返回:
            bool: 是否成功
        """
        with self._lock:
            if feature not in FEATURE_LIST:
                return False
            self._global_state[feature] = enabled
            if persist:
                if not self._save_to_config(feature, enabled):
                    logger.warning(
                        f"功能 {feature} 无配置映射，开关仅写入内存，"
                        f"重启后将失效",
                        command="AI",
                    )
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
        with self._lock:
            if not self._initialized:
                self.initialize()
            return [
                FeatureStatus(
                    name=feature,
                    enabled=self._global_state.get(feature, True),
                    config_key=_config_key_str(feature),
                )
                for feature in FEATURE_LIST
            ]

    def health_check(self) -> SwitchHealth:
        """功能体检：返回所有功能状态与计数

        返回:
            dict: 体检报告
        """
        with self._lock:
            if not self._initialized:
                self.initialize()

            total = len(FEATURE_LIST)
            enabled_count = sum(
                1 for v in self._global_state.values() if v
            )
            disabled_features = [
                f
                for f in FEATURE_LIST
                if not self._global_state.get(f, True)
            ]
            return {
                "total_features": total,
                "enabled_count": enabled_count,
                "disabled_count": total - enabled_count,
                "disabled_features": disabled_features,
                "features": [
                    {
                        "name": f,
                        "enabled": self._global_state.get(f, True),
                        "config_key": _config_key_str(f),
                    }
                    for f in FEATURE_LIST
                ],
            }


runtime_switch = RuntimeSwitchManager()
"""运行时开关管理器单例"""
