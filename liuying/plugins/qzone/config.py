"""QZone 插件配置模块

定义注册到 plugins2config.yaml 的 QZone 配置项列表，
以及统一的配置读取封装 get_config。
"""

from typing import Any

from liuying.configs.config import Config as ConfigManager
from liuying.configs.utils import RegisterConfig

__all__ = ["PluginConfig", "get_config"]

_MODULE = "QZONE"
"""配置模块名"""


PluginConfig: list[RegisterConfig] = [
    RegisterConfig(
        key="QZONE_ENABLED",
        value=False,
        module=_MODULE,
        help="是否启用QQ空间模块",
        default_value=False,
        type=bool,
    ),
]
"""QZone 插件配置项列表（注册到 plugins2config.yaml 的 QZONE 模块）"""


def get_config(key: str, default: Any = None) -> Any:
    """读取QZone插件配置值

    直接对接流萤配置系统 ConfigsManager，支持自动类型转换与默认值。

    参数:
        key: 配置键名（大小写不敏感，内部会upper）
        default: 默认值

    返回:
        Any: 配置值，未找到时返回默认值
    """
    return ConfigManager.get_config(_MODULE, key, default)
