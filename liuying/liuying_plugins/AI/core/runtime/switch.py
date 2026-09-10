"""AI运行时开关管理器

提供内存级开关 + 配置文件持久化（通过 ConfigManager.set_config）。
支持总开关与子功能开关，可按全局/群组/用户维度独立控制。

开关优先级（高到低）：
1. 用户级开关（user_overrides）
2. 群组级开关（group_overrides）
3. 全局开关（global_state，从配置加载）
"""

from dataclasses import dataclass, field
import threading
from typing import Any

from liuying.configs.config import Config as ConfigManager
from liuying.utils.log import logger

from ...config import get_config

__all__ = [
    "FEATURE_LIST",
    "FeatureStatus",
    "RuntimeSwitchManager",
    "runtime_switch",
]

_MODULE = "AI"
"""配置模块名"""


FEATURE_LIST: tuple[str, ...] = (
    "ai",
    "agent",
    "memory",
    "vision",
    "tts",
    "sticker",
    "proactive",
    "social_intelligence",
    "diary",
    "webui",
    "web_search",
    "knowledge",
    "group_profile",
    "emotion",
    "safety_filter",
    "humanize",
    "fragment",
)
"""受运行时开关管理的子功能名列表"""


_CONFIG_KEY_MAP: dict[str, tuple[str, str | None]] = {
    "ai": ("ENABLE_AI", None),
    "agent": ("AGENT", "enabled"),
    "memory": ("MEMORY_ENABLED", None),
    "vision": ("VISION", "enabled"),
    "tts": ("TTS", "enabled"),
    "sticker": ("STICKER", "enabled"),
    "proactive": ("PROACTIVE", "enabled"),
    "social_intelligence": ("SOCIAL_INTELLIGENCE_ENABLED", None),
    "diary": ("DIARY_ENABLED", None),
    "webui": ("WEBUI_ENABLED", None),
    "safety_filter": ("SAFETY_FILTER_ENABLED", None),
}
"""功能名到配置键的映射（用于读写配置文件）

值为 (config_key, sub_key) 元组：
- sub_key 为 None 时直接读写 config_key
- sub_key 不为 None 时读写 config_key 配置组下的 sub_key 子键
"""


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
        source: 状态来源（global/group/user/config）
        config_key: 对应的配置键，无则空串
    """

    name: str
    enabled: bool
    source: str = "global"
    config_key: str = ""


@dataclass(slots=True)
class _ScopeOverrides:
    """作用域覆盖

    Attributes:
        user: 用户级覆盖字典 {feature: bool}
    """

    user: dict[str, bool] = field(default_factory=dict)


class RuntimeSwitchManager:
    """运行时开关管理器

    管理AI插件的总开关与子功能开关，支持全局/群组/用户三层覆盖。
    全局状态从配置文件加载，运行时修改可持久化回配置文件。
    """

    def __init__(self) -> None:
        """初始化运行时开关管理器"""
        self._global_state: dict[str, bool] = {}
        """全局开关状态"""
        self._user_overrides: dict[str, _ScopeOverrides] = {}
        """用户级开关覆盖 {user_id: _ScopeOverrides}"""
        self._group_overrides: dict[str, dict[str, bool]] = {}
        """群组级开关覆盖 {group_id: {feature: bool}}"""
        self._lock = threading.RLock()
        """并发锁"""
        self._initialized = False
        """是否已初始化"""

    def initialize(self) -> None:
        """从配置文件加载全局开关状态"""
        with self._lock:
            if self._initialized:
                return
            self._global_state = {}
            for feature in FEATURE_LIST:
                self._global_state[feature] = self._load_from_config(
                    feature
                )
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

    def is_enabled(
        self,
        feature: str,
        *,
        user_id: str | None = None,
        group_id: str | None = None,
    ) -> bool:
        """查询功能是否启用

        优先级：用户级 > 群组级 > 全局。

        参数:
            feature: 功能名
            user_id: 用户ID，None不查用户级
            group_id: 群组ID，None不查群组级

        返回:
            bool: 是否启用
        """
        with self._lock:
            if not self._initialized:
                self.initialize()

            if user_id:
                user_cfg = self._user_overrides.get(user_id)
                if user_cfg and feature in user_cfg.user:
                    return user_cfg.user[feature]

            if group_id:
                group_cfg = self._group_overrides.get(group_id)
                if group_cfg and feature in group_cfg:
                    return group_cfg[feature]

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

    def set_group(
        self, group_id: str, feature: str, enabled: bool
    ) -> bool:
        """设置群组级开关覆盖

        参数:
            group_id: 群组ID
            feature: 功能名
            enabled: 是否启用

        返回:
            bool: 是否成功
        """
        with self._lock:
            if feature not in FEATURE_LIST or not group_id:
                return False
            self._group_overrides.setdefault(group_id, {})[
                feature
            ] = enabled
            logger.info(
                f"群 {group_id} 开关 {feature}={enabled}",
                command="AI",
            )
            return True

    def set_user(
        self, user_id: str, feature: str, enabled: bool
    ) -> bool:
        """设置用户级开关覆盖

        参数:
            user_id: 用户ID
            feature: 功能名
            enabled: 是否启用

        返回:
            bool: 是否成功
        """
        with self._lock:
            if feature not in FEATURE_LIST or not user_id:
                return False
            self._user_overrides.setdefault(
                user_id, _ScopeOverrides()
            ).user[feature] = enabled
            logger.info(
                f"用户 {user_id} 开关 {feature}={enabled}",
                command="AI",
            )
            return True

    def clear_group(self, group_id: str, feature: str) -> bool:
        """清除群组级覆盖（回退到全局）

        参数:
            group_id: 群组ID
            feature: 功能名

        返回:
            bool: 是否成功
        """
        with self._lock:
            group_cfg = self._group_overrides.get(group_id)
            if group_cfg and feature in group_cfg:
                group_cfg.pop(feature, None)
                if not group_cfg:
                    self._group_overrides.pop(group_id, None)
                return True
            return False

    def clear_user(self, user_id: str, feature: str) -> bool:
        """清除用户级覆盖（回退到群组/全局）

        参数:
            user_id: 用户ID
            feature: 功能名

        返回:
            bool: 是否成功
        """
        with self._lock:
            user_cfg = self._user_overrides.get(user_id)
            if user_cfg and feature in user_cfg.user:
                user_cfg.user.pop(feature, None)
                if not user_cfg.user:
                    self._user_overrides.pop(user_id, None)
                return True
            return False

    def get_status(
        self,
        *,
        user_id: str | None = None,
        group_id: str | None = None,
    ) -> list[FeatureStatus]:
        """获取所有功能的状态

        参数:
            user_id: 用户ID
            group_id: 群组ID

        返回:
            list[FeatureStatus]: 功能状态列表
        """
        with self._lock:
            if not self._initialized:
                self.initialize()

            result: list[FeatureStatus] = []
            for feature in FEATURE_LIST:
                config_key = _config_key_str(feature)

                if user_id:
                    user_cfg = self._user_overrides.get(user_id)
                    if user_cfg and feature in user_cfg.user:
                        result.append(
                            FeatureStatus(
                                name=feature,
                                enabled=user_cfg.user[feature],
                                source="user",
                                config_key=config_key,
                            )
                        )
                        continue

                if group_id:
                    group_cfg = self._group_overrides.get(group_id)
                    if group_cfg and feature in group_cfg:
                        result.append(
                            FeatureStatus(
                                name=feature,
                                enabled=group_cfg[feature],
                                source="group",
                                config_key=config_key,
                            )
                        )
                        continue

                result.append(
                    FeatureStatus(
                        name=feature,
                        enabled=self._global_state.get(feature, True),
                        source="global",
                        config_key=config_key,
                    )
                )
            return result

    def health_check(self) -> dict[str, Any]:
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
                f for f in FEATURE_LIST
                if not self._global_state.get(f, True)
            ]
            return {
                "total_features": total,
                "enabled_count": enabled_count,
                "disabled_count": total - enabled_count,
                "disabled_features": disabled_features,
                "group_overrides_count": len(self._group_overrides),
                "user_overrides_count": len(self._user_overrides),
                "features": [
                    {
                        "name": f,
                        "enabled": self._global_state.get(f, True),
                        "config_key": _config_key_str(f),
                    }
                    for f in FEATURE_LIST
                ],
            }

    def reset_all(self) -> None:
        """重置所有覆盖（保留全局配置）"""
        with self._lock:
            self._user_overrides.clear()
            self._group_overrides.clear()
            logger.info(
                "运行时开关覆盖已全部重置",
                command="AI",
            )


runtime_switch = RuntimeSwitchManager()
"""运行时开关管理器单例"""
