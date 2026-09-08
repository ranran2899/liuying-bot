"""组件与主题资源的路径解析器。

资源解析回退顺序：
1. 相对路径（./ 或 ../ 开头，相对当前模板所在组件）
   a. 皮肤目录资源（组件位于 skins/ 下时）
   b. 页面级主题目录资源（组件位于 pages 下带主题子目录时）
   c. 当前主题的组件资源
   d. 默认主题的组件资源（回退）
2. 全局路径
   a. 当前主题全局资源（assets/ 下）
   b. 默认主题全局资源（回退）
3. 命名空间路径（@namespace/... 前缀），交由 Jinja 加载器定位
"""

from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from jinja2 import TemplateNotFound

from liuying.configs.path_config import THEMES_PATH
from liuying.services.log import logger

if TYPE_CHECKING:
    from .manager import ThemeManager


class ResourceResolver:
    """为模板中的 asset() 调用提供完整的路径回退与 URI 解析。"""

    def __init__(self, theme_manager: "ThemeManager") -> None:
        """初始化解析器。

        参数:
            theme_manager: 主题管理器，提供当前主题与模板加载器。
        """
        self.theme_manager = theme_manager

    def resolve_asset_uri(self, asset_path: str, template_name: str) -> str:
        """解析资源路径为绝对文件 URI。

        参数:
            asset_path: 模板中引用的资源路径（相对/全局/命名空间）。
            template_name: 发起引用的模板名称，用于相对路径定位。

        返回:
            str: 资源的绝对文件 URI，找不到时返回空字符串。
        """
        theme = self.theme_manager.current_theme
        if not theme:
            return ""
        if asset_path.startswith("@"):
            return self._resolve_namespace_asset(asset_path, template_name)

        candidates: list[tuple[str, Path]]
        if asset_path.startswith(("./", "..")):
            stripped = asset_path[2:] if asset_path.startswith("./") else asset_path
            candidates = self._relative_candidates(stripped, template_name)
        else:
            candidates = [
                (f"'{theme.name}' 主题全局资源", theme.assets_dir / asset_path)
            ]
            if theme.name != "default":
                candidates.append((
                    "default 主题全局资源 (回退)",
                    theme.default_assets_dir / asset_path,
                ))

        for desc, path in candidates:
            if path.exists():
                logger.debug(f"资源 '{asset_path}' -> {desc}: '{path}'")
                return path.absolute().as_uri()

        logger.warning(
            f"资源文件未找到: '{asset_path}' (模板 '{template_name}' 中引用)"
        )
        return ""

    def _relative_candidates(
        self, asset_path: str, template_name: str
    ) -> list[tuple[str, Path]]:
        """为相对路径资源生成按优先级排列的候选路径。

        参数:
            asset_path: 去除 ./ 前缀后的资源相对路径。
            template_name: 发起引用的模板名称。

        返回:
            list[tuple[str, Path]]: (来源描述, 候选路径) 的有序列表。
        """
        theme = self.theme_manager.current_theme
        if not theme:
            return []

        template_file = self._locate_template(template_name)
        if not template_file:
            return []

        candidates: list[tuple[str, Path]] = []
        component_root = self._component_root(template_file, template_name)

        # 皮肤目录内的组件：优先查找皮肤自身 assets 目录
        if "skins" in template_file.parent.parts:
            candidates.append((
                f"'{theme.name}' 主题皮肤资源",
                template_file.parent / "assets" / asset_path,
            ))

        # 页面级主题目录（组件位于 pages/xxx/<theme>/ 之下）的资源
        page_theme_dir = self._page_theme_dir(template_file, component_root)
        if page_theme_dir:
            candidates.append((
                f"'{theme.name}' 主题页面主题资源",
                page_theme_dir / "assets" / asset_path,
            ))

        candidates.append((
            f"'{theme.name}' 主题组件资源",
            component_root / "assets" / asset_path,
        ))
        if theme.name != "default":
            default_component_root = (
                theme.default_root / component_root.relative_to(theme.root)
                if component_root.is_relative_to(theme.root)
                else theme.default_root / PurePosixPath(template_name).parent
            )
            candidates.append((
                "default 主题组件资源 (回退)",
                default_component_root / "assets" / asset_path,
            ))
        return candidates

    def _locate_template(self, template_name: str) -> Path | None:
        """通过 Jinja 加载器定位模板的绝对路径。

        参数:
            template_name: 模板名称。

        返回:
            Path | None: 模板物理路径，定位失败时返回 None。
        """
        loader = self.theme_manager.jinja_env.loader
        if not loader:
            return None
        try:
            _source, filepath, _uptodate = loader.get_source(
                self.theme_manager.jinja_env, template_name
            )
        except TemplateNotFound:
            return None
        return Path(filepath) if filepath else None

    def _component_root(self, template_file: Path, template_name: str) -> Path:
        """从模板物理路径向上查找包含 manifest.json 的组件根目录。

        参数:
            template_file: 模板的物理路径。
            template_name: 模板名称（仅用于回退描述）。

        返回:
            Path: 组件根目录，找不到清单时返回模板所在目录。
        """
        current = template_file.parent
        themes_depth = len(THEMES_PATH.parts)
        for _ in range(len(current.parts) - themes_depth):
            if (current / "manifest.json").exists():
                return current
            if current.parent == current:
                break
            current = current.parent
        return template_file.parent

    def _page_theme_dir(
        self, template_file: Path, component_root: Path
    ) -> Path | None:
        """当组件处于页面主题子目录时返回该目录。

        判定依据：组件根目录下存在与模板父目录同名的子目录，
        且该子目录包含页面模板文件（排除 skins 与 assets 目录，
        兼容入口为 main.html 与 dispatch.html 等分发型页面）。

        参数:
            template_file: 模板的物理路径。
            component_root: 组件根目录。

        返回:
            Path | None: 页面主题目录，不符合时返回 None。
        """
        parent = template_file.parent
        if component_root == parent or parent.name in ("skins", "assets"):
            return None
        candidate = component_root / parent.name
        if any(candidate.glob("*.html")):
            return candidate
        return None

    def _resolve_namespace_asset(
        self, asset_path: str, template_name: str
    ) -> str:
        """解析 @namespace 形式的资源路径。

        参数:
            asset_path: 以 @ 开头的命名空间资源路径。
            template_name: 发起引用的模板名称。

        返回:
            str: 资源的绝对文件 URI，未找到时返回空字符串。
        """
        env = self.theme_manager.jinja_env
        loader = env.loader
        if not loader:
            return ""
        try:
            full_path = env.join_path(asset_path, template_name)
            _source, filepath, _uptodate = loader.get_source(env, full_path)
        except TemplateNotFound:
            logger.warning(
                f"命名空间资源未找到: '{asset_path}' (模板 '{template_name}')"
            )
            return ""
        return Path(filepath).absolute().as_uri() if filepath else ""
