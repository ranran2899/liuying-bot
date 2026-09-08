"""渲染器静态配置常量。"""

from typing import Literal

# 模板上下文中的保留键，组件渲染数据若与之冲突则只能通过 data.<key> 访问
RESERVED_TEMPLATE_KEYS: frozenset[str] = frozenset({
    "data",
    "theme",
    "theme_css",
    "extra_css",
    "required_scripts",
    "required_styles",
    "frameless",
})

# 渲染配置键所属模块
CONFIG_MODULE: Literal["UI"] = "UI"

# 缓存开关与调试开关的配置键名
CACHE_CONFIG_KEY = "CACHE"
DEBUG_CONFIG_KEY = "DEBUG_MODE"

# 内存缓存过期时间（秒）
RENDER_CACHE_EXPIRE = 3600

# 模板/清单解析的超时时间（秒）
RESOLVE_TIMEOUT = 10.0
