"""流萤本体 WebUI 插件配置模块

定义注册到 plugins2config.yaml 的配置项列表，
以及统一的配置读取封装 get_config。
"""

from typing import Any

from liuying.configs.config import Config as ConfigManager
from liuying.configs.utils import RegisterConfig

__all__ = ["PluginConfig", "get_config", "set_config"]

_MODULE = "BOT_WEBUI"
"""配置模块名"""


PluginConfig: list[RegisterConfig] = [
    RegisterConfig(
        key="WEBUI_ENABLED",
        value=True,
        module=_MODULE,
        help="是否启用流萤本体 WebUI 管理控制台",
        default_value=True,
        type=bool,
    ),
    RegisterConfig(
        key="WEBUI_ACCOUNT",
        value="admin",
        module=_MODULE,
        help="WebUI 登录账号",
        default_value="admin",
        type=str,
    ),
    RegisterConfig(
        key="WEBUI_TOKEN",
        value="",
        module=_MODULE,
        help="WebUI 登录令牌（请设置为足够复杂的字符串）",
        default_value="",
        type=str,
    ),
    RegisterConfig(
        key="WEBUI_ROUTE_PREFIX",
        value="/bot",
        module=_MODULE,
        help="本体 WebUI 路由前缀",
        default_value="/bot",
        type=str,
    ),
    RegisterConfig(
        key="WEBUI_LOG_TAIL_LINES",
        value=400,
        module=_MODULE,
        help="日志查看接口返回的尾部行数上限",
        default_value=400,
        type=int,
    ),
]
"""流萤本体 WebUI 插件配置项列表"""


class ConfigHelper:
    """本体 WebUI 插件配置辅助类

    封装配置读写操作，统一对接流萤配置系统 ConfigsManager。
    """

    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        """读取本体 WebUI 插件配置值

        参数:
            key: 配置键名（大小写不敏感，内部会upper）
            default: 默认值

        返回:
            Any: 配置值，未找到时返回默认值
        """
        return ConfigManager.get_config(_MODULE, key, default)

    @staticmethod
    def set(key: str, value: Any, auto_save: bool = True) -> None:
        """写入本体 WebUI 插件配置值

        参数:
            key: 配置键名（大小写不敏感，内部会upper）
            value: 配置值
            auto_save: 是否立即持久化到文件
        """
        ConfigManager.set_config(_MODULE, key, value, auto_save=auto_save)


def get_config(key: str, default: Any = None) -> Any:
    """读取本体 WebUI 插件配置值

    参数:
        key: 配置键名
        default: 默认值

    返回:
        Any: 配置值，未找到时返回默认值
    """
    return ConfigHelper.get(key, default)


def set_config(key: str, value: Any, auto_save: bool = True) -> None:
    """写入本体 WebUI 插件配置值

    参数:
        key: 配置键名
        value: 配置值
        auto_save: 是否立即持久化到文件
    """
    ConfigHelper.set(key, value, auto_save=auto_save)
