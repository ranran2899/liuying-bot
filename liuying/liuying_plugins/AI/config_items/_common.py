"""配置项公共定义

提供配置模块名常量与 RegisterConfig 快捷工厂，供各配置域子模块复用。
"""

from liuying.configs.utils import RegisterConfig

MODULE = "AI"
"""配置模块名"""


def cfg(
    key: str,
    value: object,
    help: str,
    type: type,
) -> RegisterConfig:
    """RegisterConfig 快捷工厂

    统一注入 module 与 default_value，消除样板重复。

    参数:
        key: 配置键名
        value: 默认值
        help: 配置说明
        type: 值类型

    返回:
        RegisterConfig: 配置项
    """
    return RegisterConfig(
        key=key,
        value=value,
        module=MODULE,
        help=help,
        default_value=value,
        type=type,
    )


__all__ = ["MODULE", "RegisterConfig", "cfg"]
