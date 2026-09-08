"""主题与资源子包：主题管理、页面主题目录、资源注册与 asset 解析。

本子包承载"主题系统"职责：
- manager: ThemeManager（主题加载、模板/清单解析、组件 HTML 组装）
- catalog: ThemeCatalog（页面主题扫描、功能发现、主题商店条目）
- registry: AssetRegistry（插件运行期注册的具名资源，如 Markdown 样式）
- resolver: ResourceResolver（模板内 asset() 的路径回退与 URI 解析）
"""

from .catalog import ThemeCatalog, ThemeStoreItem, has_template_suffix
from .manager import (
    RelativePathEnvironment,
    Theme,
    ThemeManager,
    markdown_filter,
)
from .registry import AssetRegistry, asset_registry
from .resolver import ResourceResolver

__all__ = [
    "AssetRegistry",
    "RelativePathEnvironment",
    "ResourceResolver",
    "Theme",
    "ThemeCatalog",
    "ThemeManager",
    "ThemeStoreItem",
    "asset_registry",
    "has_template_suffix",
    "markdown_filter",
]
