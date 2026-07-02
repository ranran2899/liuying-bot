from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from jinja2 import TemplateNotFound

from liuying.configs.path_config import THEMES_PATH
from liuying.services.log import logger

if TYPE_CHECKING:
    from .theme import ThemeManager


class ResourceResolver:
    """独立的组件和主题资源解析器。

    封装了所有复杂的路径查找和回退逻辑。

    资源解析遵循以下回退顺序:

    1. 相对路径 (./): 组件内部资源
       a. 皮肤资源: 当前组件的皮肤目录
       b. 当前主题组件资源: 当前激活主题的组件根目录
       c. 默认主题组件资源: default 主题中对应的组件目录

    2. 全局路径: 主题的全局资源
       a. 当前主题全局资源: 当前激活主题的根 assets 目录
       b. 默认主题全局资源: default 主题的根 assets 目录
    """

    def __init__(self, theme_manager: "ThemeManager"):
        self.theme_manager = theme_manager

    def _find_component_root(self, start_path: Path) -> Path:
        """从给定路径向上查找包含 manifest.json 的组件根目录。"""
        current_path = start_path.parent
        themes_root_parts = len(THEMES_PATH.parts)
        for _ in range(len(current_path.parts) - themes_root_parts):
            if (current_path / "manifest.json").exists():
                return current_path
            if current_path.parent == current_path:
                break
            current_path = current_path.parent
        return start_path.parent

    def _search_paths_for_relative_asset(
        self, asset_path: str, parent_template_name: str
    ) -> list[tuple[str, Path]]:
        """为相对路径资源生成所有可能的查找路径元组。

        支持扁平化主题目录和传统 skins 目录的回退逻辑。
        """
        if not self.theme_manager.current_theme:
            return []

        paths_to_check: list[tuple[str, Path]] = []
        current_theme_name = self.theme_manager.current_theme.name
        current_theme_root = self.theme_manager.current_theme.assets_dir.parent
        default_theme_root = self.theme_manager.current_theme.default_assets_dir.parent

        if not self.theme_manager.jinja_env.loader:
            return []

        try:
            source_info = self.theme_manager.jinja_env.loader.get_source(
                self.theme_manager.jinja_env, parent_template_name
            )
        except TemplateNotFound:
            return []

        if not source_info[1]:
            return []

        parent_template_abs_path = Path(source_info[1])
        parent_abs_posix = parent_template_abs_path.as_posix()
        component_logical_root = PurePosixPath(parent_template_name).parent

        in_skin = "/skins/" in parent_abs_posix
        in_theme = False
        theme_dir_name = None

        if not in_skin:
            parent_dir_name = parent_template_abs_path.parent.name
            parent_parent_dir = parent_template_abs_path.parent.parent
            if (
                parent_parent_dir.exists()
                and (parent_parent_dir / "manifest.json").exists()
                and parent_dir_name not in ("skins", "assets")
                and parent_dir_name != parent_parent_dir.name
            ):
                manifest_check = parent_parent_dir / parent_dir_name / "main.html"
                root_check = parent_parent_dir / "main.html"
                if not (manifest_check.exists() and not root_check.exists()):
                    if not root_check.exists():
                        in_theme = True
                        theme_dir_name = parent_dir_name

        match (in_skin, in_theme, theme_dir_name):
            case (True, _, _):
                skin_dir = parent_template_abs_path.parent
                paths_to_check.append((
                    f"'{current_theme_name}' 主题皮肤资源",
                    skin_dir / "assets" / asset_path,
                ))
            case (False, True, dir_name) if dir_name:
                theme_sub_dir = parent_template_abs_path.parent
                paths_to_check.append((
                    f"'{current_theme_name}' 主题页面主题资源 ({dir_name})",
                    theme_sub_dir / "assets" / asset_path,
                ))
                default_dir = theme_sub_dir.parent / "default"
                if default_dir.is_dir():
                    paths_to_check.append((
                        f"'{current_theme_name}' 主题默认页面资源 (回退)",
                        default_dir / "assets" / asset_path,
                    ))
            case _:
                pass

        paths_to_check.append((
            f"'{current_theme_name}' 主题组件资源",
            current_theme_root / component_logical_root / "assets" / asset_path,
        ))

        if current_theme_name != "default":
            paths_to_check.append((
                "'default' 主题组件资源 (回退)",
                default_theme_root / component_logical_root / "assets" / asset_path,
            ))
        return paths_to_check

    def resolve_asset_uri(self, asset_path: str, current_template_name: str) -> str:
        """解析资源路径，实现完整的回退逻辑，并返回可用的URI。"""
        if (
            not self.theme_manager.current_theme
            or not self.theme_manager.jinja_env.loader
        ):
            return ""

        if asset_path.startswith("@"):
            return self._resolve_namespace_asset(
                asset_path, current_template_name
            )

        search_paths: list[tuple[str, Path]] = []
        match asset_path[:2]:
            case "./":
                search_paths.extend(
                    self._search_paths_for_relative_asset(
                        asset_path[2:], current_template_name
                    )
                )
            case "..":
                search_paths.extend(
                    self._search_paths_for_relative_asset(
                        asset_path, current_template_name
                    )
                )
            case _:
                search_paths.append((
                    f"'{self.theme_manager.current_theme.name}' 主题全局资源",
                    self.theme_manager.current_theme.assets_dir / asset_path,
                ))
                if self.theme_manager.current_theme.name != "default":
                    default_dir = (
                        self.theme_manager.current_theme.default_assets_dir
                    )
                    search_paths.append((
                        "'default' 主题全局资源 (回退)",
                        default_dir / asset_path,
                    ))

        for source_desc, path in search_paths:
            if path.exists():
                logger.debug(
                    f"解析资源 '{asset_path}' -> 找到 {source_desc}: '{path}'"
                )
                return path.absolute().as_uri()

        logger.warning(
            f"资源文件未找到: '{asset_path}' "
            f"(在模板 '{current_template_name}' 中引用)"
        )
        return ""

    def _resolve_namespace_asset(
        self, asset_path: str, current_template_name: str
    ) -> str:
        """解析命名空间资源（以@开头的路径）。"""
        try:
            full_asset_path = self.theme_manager.jinja_env.join_path(
                asset_path, current_template_name
            )
            _source, file_abs_path, _uptodate = (
                self.theme_manager.jinja_env.loader.get_source(
                    self.theme_manager.jinja_env, full_asset_path
                )
            )
            if file_abs_path:
                logger.debug(
                    f"Jinja Loader resolved asset "
                    f"'{asset_path}'->'{file_abs_path}'"
                )
                return Path(file_abs_path).absolute().as_uri()
        except TemplateNotFound:
            logger.warning(
                f"资源文件在命名空间中未找到: '{asset_path}'"
                f"(在模板 '{current_template_name}' 中引用)"
            )
        return ""
