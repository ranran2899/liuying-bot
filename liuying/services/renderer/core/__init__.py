"""渲染器核心子包：协议契约、静态配置、渲染上下文与通用工具。

本子包是渲染体系的最底层，被 theme 与 render 子包依赖，
自身不依赖任何渲染业务模块。
"""

from .config import (
    CACHE_CONFIG_KEY,
    CONFIG_MODULE,
    DEBUG_CONFIG_KEY,
    RENDER_CACHE_EXPIRE,
    RESERVED_TEMPLATE_KEYS,
    RESOLVE_TIMEOUT,
)
from .context import RenderContext
from .protocols import Renderable, RenderResult, ScreenshotEngine

__all__ = [
    "CACHE_CONFIG_KEY",
    "CONFIG_MODULE",
    "DEBUG_CONFIG_KEY",
    "RENDER_CACHE_EXPIRE",
    "RESERVED_TEMPLATE_KEYS",
    "RESOLVE_TIMEOUT",
    "RenderContext",
    "RenderResult",
    "Renderable",
    "ScreenshotEngine",
]
