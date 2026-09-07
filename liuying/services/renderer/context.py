"""单次渲染任务的上下文对象。"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .protocols import Renderable, ScreenshotEngine

if TYPE_CHECKING:
    from .service import RendererService
    from .theme import ThemeManager


@dataclass(slots=True)
class RenderContext:
    """承载一次渲染的全部状态，包括运行环境与过程级缓存。"""

    renderer: "RendererService | None"
    theme_manager: "ThemeManager"
    screenshot_engine: ScreenshotEngine | None
    component: Renderable
    use_cache: bool
    render_options: dict[str, Any]
    # 已解析的模板路径缓存，键为 "组件路径::变体"
    resolved_template_paths: dict[str, str] = field(default_factory=dict)
    # 已解析的 Markdown 样式路径缓存
    resolved_style_paths: dict[str, Path | None] = field(default_factory=dict)
    # 递归收集到的资源与样式
    collected_asset_styles: set[str] = field(default_factory=set)
    collected_scripts: set[str] = field(default_factory=set)
    collected_inline_css: list[str] = field(default_factory=list)
    # 已处理组件的 id 集合，防止循环引用导致的重复收集
    processed_components: set[int] = field(default_factory=set)
