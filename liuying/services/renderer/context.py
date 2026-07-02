from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .protocols import Renderable, ScreenshotEngine

if TYPE_CHECKING:
    from .service import RendererService
    from .theme import ThemeManager


@dataclass(slots=True)
class RenderContext:
    """单次渲染任务的上下文对象，用于状态传递和缓存。"""

    renderer: "RendererService | None"
    theme_manager: "ThemeManager"
    screenshot_engine: ScreenshotEngine | None
    component: Renderable
    use_cache: bool
    render_options: dict[str, Any]
    resolved_template_paths: dict[str, str] = field(default_factory=dict)
    resolved_style_paths: dict[str, Path | None] = field(default_factory=dict)
    collected_asset_styles: set[str] = field(default_factory=set)
    collected_scripts: set[str] = field(default_factory=set)
    collected_inline_css: list[str] = field(default_factory=list)
    processed_components: set[int] = field(default_factory=set)
