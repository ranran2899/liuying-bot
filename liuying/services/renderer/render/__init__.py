"""渲染执行子包：渲染门面、依赖收集、两级缓存与截图引擎。

本子包承载"渲染执行"职责：
- service: RendererService（统一渲染门面与编排）
- dependency: DependencyCollector（组件树样式/脚本/内联 CSS 收集）
- cache: RenderCache（内存 + 磁盘两级渲染缓存）
- engine: PlaywrightEngine（基于 htmlrender 的截图后端）
"""

from .cache import RenderCache, render_cache_key
from .dependency import DependencyCollector
from .engine import PlaywrightEngine, get_screenshot_engine
from .service import RendererService

__all__ = [
    "DependencyCollector",
    "PlaywrightEngine",
    "RenderCache",
    "RendererService",
    "get_screenshot_engine",
    "render_cache_key",
]
