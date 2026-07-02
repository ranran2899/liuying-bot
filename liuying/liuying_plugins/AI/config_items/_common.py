"""配置项公共定义

提供配置模块名常量，供各配置域子模块复用。
"""

from liuying.configs.utils import RegisterConfig

MODULE = "AI"
"""配置模块名"""

__all__ = ["MODULE", "RegisterConfig"]
