import asyncio
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from jinja2 import (
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    PrefixLoader,
    TemplateNotFound,
    pass_context,
)
import markdown
from markupsafe import Markup
import orjson as json
from pydantic import BaseModel

from liuying.configs.path_config import THEMES_PATH
from liuying.services.log import logger
from liuying.services.renderer.protocols import Renderable
from liuying.services.renderer.registry import asset_registry
from liuying.utils.pydantic_compat import model_dump

if TYPE_CHECKING:
    from .context import RenderContext

from .config import RESERVED_TEMPLATE_KEYS
from .resolver import ResourceResolver
from .utils import deep_merge_dict

_TEMPLATE_RESOLVE_TIMEOUT = 10.0


class RelativePathEnvironment(Environment):
    """自定义 Jinja2 环境，支持模板间的相对路径引用。"""

    def join_path(self, template: str, parent: str) -> str:
        if template.startswith("./") or template.startswith("../"):
            return str(
                PurePosixPath(parent).parent / template
            )
        return super().join_path(template, parent)


class Theme(BaseModel):
    """主题数据模型。"""

    name: str
    palette: dict[str, Any]
    style_css: str = ""
    assets_dir: Path
    default_assets_dir: Path


class ThemeStoreItem(BaseModel):
    """主题商店条目模型。"""

    feature: str
    feature_label: str
    theme_name: str
    theme_label: str
    display_name: str
    price: int
    page_path: str


class ThemeManager:
    """主题管理器，负责UI主题的加载、解析和模板渲染。"""

    def __init__(self, env: Environment):
        self.jinja_env = env
        self.current_theme: Theme | None = None

        self.jinja_env.globals["render"] = self._global_render_component
        self.jinja_env.globals["asset"] = self._create_asset_loader()
        self.jinja_env.globals["resolve_template"] = (
            self._resolve_component_template
        )

        self.jinja_env.filters["md"] = self._markdown_filter

        self._manifest_cache: dict[str, Any] = {}
        self._manifest_cache_lock = asyncio.Lock()
        self._page_themes_cache: dict[str, list[str]] = {}
        self._theme_css_cache: dict[str, str] = {}
        self._template_resolve_cache: dict[str, str] = {}
        self._store_cache: list[ThemeStoreItem] | None = None

    def list_available_themes(self) -> list[str]:
        """扫描主题目录并返回所有可用的全局主题名称。"""
        if not THEMES_PATH.is_dir():
            return []
        return [
            d.name
            for d in THEMES_PATH.iterdir()
            if d.is_dir() and (d / "palette.json").exists()
        ]

    def list_page_themes(self, page_path: str) -> list[str]:
        """扫描页面目录并返回所有可用的页面级主题名称（带缓存）。"""
        if page_path in self._page_themes_cache:
            return self._page_themes_cache[page_path]

        if not self.current_theme:
            return ["default"]
        theme_dir = self.current_theme.assets_dir.parent / page_path
        if not theme_dir.is_dir():
            self._page_themes_cache[page_path] = ["default"]
            return ["default"]

        themes = [
            d.name
            for d in theme_dir.iterdir()
            if d.is_dir() and (d / "theme.json").exists()
        ]
        result = sorted(themes) if themes else ["default"]
        self._page_themes_cache[page_path] = result
        return result

    def _load_theme_json(
        self, page_path: str, theme_name: str
    ) -> dict[str, Any] | None:
        """加载指定页面主题的 theme.json 配置。

        优先从当前主题目录加载，回退到默认主题目录。

        参数:
            page_path: 页面路径，如 "pages/builtin/signIn"
            theme_name: 主题名称，如 "pink"

        返回:
            dict | None: 主题配置字典，加载失败返回 None
        """
        if not self.current_theme:
            return None
        theme_json_path = (
            self.current_theme.assets_dir.parent
            / page_path
            / theme_name
            / "theme.json"
        )
        if not theme_json_path.exists():
            default_theme_json = (
                self.current_theme.default_assets_dir.parent
                / page_path
                / theme_name
                / "theme.json"
            )
            if not default_theme_json.exists():
                return None
            theme_json_path = default_theme_json
        try:
            return json.loads(theme_json_path.read_bytes())
        except (json.JSONDecodeError, OSError):
            return None

    def get_theme_price(self, page_path: str, theme_name: str) -> int:
        """获取指定页面主题的价格。

        参数:
            page_path: 页面路径，如 "pages/builtin/bank"
            theme_name: 主题名称，如 "pink"

        返回:
            int: 主题价格，默认主题返回0，未找到时返回0
        """
        if theme_name == "default":
            return 0
        data = self._load_theme_json(page_path, theme_name)
        return data.get("price", 0) if data else 0

    def get_theme_label(
        self, page_path: str, theme_name: str
    ) -> str:
        """获取指定页面主题的中文标签。

        参数:
            page_path: 页面路径
            theme_name: 主题名称

        返回:
            str: 中文标签，未配置时返回主题名称本身
        """
        if theme_name == "default":
            return "默认"
        data = self._load_theme_json(page_path, theme_name)
        if data:
            return data.get("label", theme_name)
        return theme_name

    def resolve_theme_name(
        self, page_path: str, label_or_name: str
    ) -> str | None:
        """将中文标签或英文名称解析为主题目录名。

        支持中文标签（如"粉色"）和英文主题名（如"pink"）双向解析。

        参数:
            page_path: 页面路径
            label_or_name: 中文标签或英文主题名

        返回:
            str | None: 匹配的主题目录名，未匹配返回 None
        """
        available_themes = self.list_page_themes(page_path)
        for t_name in available_themes:
            if t_name == label_or_name:
                return t_name
            label = self.get_theme_label(page_path, t_name)
            if label == label_or_name:
                return t_name
        return None

    def resolve_feature_key(self, label_or_key: str) -> str | None:
        """将中文功能标签或英文功能键解析为功能键。

        支持中文标签（如"签到"）和英文键（如"sign"）双向解析。

        参数:
            label_or_key: 中文功能标签或英文功能键

        返回:
            str | None: 匹配的功能键，未匹配返回 None
        """
        features = self.discover_features()
        for f_key, info in features.items():
            if f_key == label_or_key:
                return f_key
            if info.get("label") == label_or_key:
                return f_key
        return None

    def get_store_items(self) -> list[ThemeStoreItem]:
        """获取主题商店所有可购买的主题条目。

        返回:
            list[ThemeStoreItem]: 商店条目列表
        """
        if self._store_cache is not None:
            return self._store_cache

        features = self.discover_features()
        items: list[ThemeStoreItem] = []

        for f_key, info in sorted(features.items()):
            page_path = info["page_path"]
            f_label = info["label"]
            themes = self.list_page_themes(page_path)

            for t_name in themes:
                data = self._load_theme_json(page_path, t_name)
                if data:
                    display_name = data.get("name", t_name)
                    price = data.get("price", 0)
                    theme_label = data.get("label", t_name)
                else:
                    display_name = t_name
                    price = 0
                    theme_label = "默认" if t_name == "default" else t_name

                items.append(ThemeStoreItem(
                    feature=f_key,
                    feature_label=f_label,
                    theme_name=t_name,
                    theme_label=theme_label,
                    display_name=display_name,
                    price=price,
                    page_path=page_path,
                ))

        self._store_cache = items
        return items

    def clear_store_cache(self) -> None:
        """清除主题商店缓存。"""
        self._store_cache = None

    def discover_features(self) -> dict[str, dict[str, str]]:
        """自动扫描 pages/builtin 目录，从 manifest.json 发现功能。"""
        if not self.current_theme:
            return {}
        builtin_dir = (
            self.current_theme.assets_dir.parent / "pages" / "builtin"
        )
        if not builtin_dir.is_dir():
            return {}

        features: dict[str, dict[str, str]] = {}
        for page_dir in builtin_dir.iterdir():
            if not page_dir.is_dir():
                continue
            manifest_path = page_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                manifest = json.loads(manifest_path.read_bytes())
            except (json.JSONDecodeError, OSError):
                continue
            feature = manifest.get("feature")
            if not feature:
                continue
            features[feature] = {
                "page_path": f"pages/builtin/{page_dir.name}",
                "label": manifest.get("feature_label", feature),
            }
        return features

    async def resolve_user_variant(
        self, page_path: str, user_id: str
    ) -> str | None:
        """根据页面路径和用户ID自动解析用户的主题变体。"""
        if not self.current_theme:
            return None
        manifest_path = (
            self.current_theme.assets_dir.parent
            / page_path
            / "manifest.json"
        )
        if not manifest_path.exists():
            return None
        try:
            manifest = json.loads(manifest_path.read_bytes())
        except (json.JSONDecodeError, OSError):
            return None
        feature = manifest.get("feature")
        if not feature:
            return None

        from liuying.models._user.user_theme import UserTheme

        current = await UserTheme.get_current_theme(user_id, feature)
        return current if current != "default" else None

    @staticmethod
    def _get_base_entrypoint(theme_dir: Path) -> str:
        """从基础 manifest.json 获取入口文件名。"""
        manifest_path = theme_dir / "manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_bytes())
                return manifest.get("entrypoint", "main.html")
            except (json.JSONDecodeError, OSError):
                pass
        return "main.html"

    def clear_cache(self) -> None:
        """清除所有缓存。"""
        self._manifest_cache.clear()
        self._page_themes_cache.clear()
        self._theme_css_cache.clear()
        self._template_resolve_cache.clear()
        self._store_cache = None
        logger.debug("主题管理器缓存已全部清除")

    def _create_asset_loader(self) -> Callable[..., str]:
        """创建 Jinja2 中的 asset() 函数闭包。"""
        resolver = ResourceResolver(self)

        @pass_context
        def asset_loader(ctx, asset_path: str) -> str:
            if not ctx.name:
                logger.warning(
                    "Jinja2 上下文缺少模板名称，无法进行资源解析。"
                )
                return resolver.resolve_asset_uri(
                    asset_path, "unknown_template"
                )
            return resolver.resolve_asset_uri(asset_path, ctx.name)

        return asset_loader

    def _create_standalone_asset_loader(
        self, local_base_path: Path
    ) -> Callable[[str], str]:
        """为独立模板创建资源加载器。"""
        def asset_loader(asset_path: str) -> str:
            path = (
                Path(asset_path)
                if Path(asset_path).is_absolute()
                else (local_base_path / asset_path).resolve()
            )
            return path.as_uri() if path.exists() else ""

        return asset_loader

    async def _global_render_component(
        self, component: Renderable | None
    ) -> str:
        """Jinja2 全局函数，在模板内部渲染子组件。"""
        if not component:
            return ""
        try:
            from .context import RenderContext

            mock_context = RenderContext(
                renderer=None,
                theme_manager=self,
                screenshot_engine=None,
                component=component,
                use_cache=False,
                render_options={},
            )
            template_path = await self._resolve_component_template(
                component, mock_context
            )
            template = self.jinja_env.get_template(template_path)

            template_context = {
                "data": component,
                "frameless": True,
            }
            render_data = component.get_render_data()
            template_context.update(render_data)

            return Markup(
                await template.render_async(**template_context)
            )
        except Exception as e:
            logger.error(
                f"在全局 render 函数中渲染组件 "
                f"'{component.__class__.__name__}' 失败",
                e=e,
            )
            return (
                f"<!-- 组件渲染失败{component.__class__.__name__}: {e} -->"
            )

    @staticmethod
    def _markdown_filter(text: str) -> str:
        """将 Markdown 文本转换为 HTML 的 Jinja2 过滤器。"""
        if not isinstance(text, str):
            return ""
        return markdown.markdown(
            text,
            extensions=[
                "pymdownx.tasklist",
                "tables",
                "fenced_code",
                "codehilite",
                "mdx_math",
                "pymdownx.tilde",
            ],
            extension_configs={
                "mdx_math": {"enable_dollar_delimiter": True}
            },
        )

    async def load_theme(self, theme_name: str = "default"):
        """加载指定主题。"""
        theme_dir = THEMES_PATH / theme_name
        if not theme_dir.is_dir():
            logger.error(
                f"主题 '{theme_name}' 不存在，将回退到默认主题。"
            )
            if theme_name == "default":
                raise FileNotFoundError("默认主题 'default' 未找到！")
            theme_name = "default"
            theme_dir = THEMES_PATH / "default"

        default_palette_path = THEMES_PATH / "default" / "palette.json"
        default_palette = (
            json.loads(default_palette_path.read_bytes())
            if default_palette_path.exists()
            else {}
        )
        if self.jinja_env.loader and isinstance(
            self.jinja_env.loader, ChoiceLoader
        ):
            current_loaders = list(self.jinja_env.loader.loaders)
            if len(current_loaders) > 1 and isinstance(
                current_loaders[0], PrefixLoader
            ):
                prefix_loader = current_loaders[0]
                new_theme_loader = FileSystemLoader(
                    [str(theme_dir), str(THEMES_PATH / "default")]
                )
                self.jinja_env.loader.loaders = [
                    prefix_loader, new_theme_loader
                ]

        palette_path = theme_dir / "palette.json"
        palette = (
            json.loads(palette_path.read_bytes())
            if palette_path.exists()
            else {}
        )

        self.current_theme = Theme(
            name=theme_name,
            palette=palette,
            assets_dir=theme_dir / "assets",
            default_assets_dir=THEMES_PATH / "default" / "assets",
        )
        theme_context_dict = {
            "name": theme_name,
            "palette": palette,
            "assets_dir": theme_dir / "assets",
            "default_assets_dir": THEMES_PATH / "default" / "assets",
        }
        self.jinja_env.globals["theme"] = theme_context_dict
        self.jinja_env.globals["default_theme_palette"] = default_palette
        logger.info(f"主题管理器已加载主题: {theme_name}")

    async def _resolve_component_template(
        self, component: Renderable, context: "RenderContext"
    ) -> str:
        """智能解析组件模板路径，支持扁平化主题和传统皮肤目录。

        包含超时保护，防止模板解析长时间阻塞。
        """
        component_path_base = str(component.template_name)

        variant = getattr(component, "variant", None)
        cache_key = f"{component_path_base}::{variant or 'default'}"
        if cached_path := context.resolved_template_paths.get(cache_key):
            return cached_path

        if PurePosixPath(component_path_base).suffix:
            try:
                self.jinja_env.get_template(component_path_base)
                return component_path_base
            except TemplateNotFound as e:
                logger.error(
                    f"指定的模板文件路径不存在: '{component_path_base}'",
                    e=e,
                )
                raise e

        try:
            base_manifest = await asyncio.wait_for(
                self.get_template_manifest(component_path_base),
                timeout=_TEMPLATE_RESOLVE_TIMEOUT,
            )
        except TimeoutError:
            logger.warning(
                f"解析组件 '{component_path_base}' 基础清单超时"
            )
            base_manifest = None

        theme_to_use = variant or (
            base_manifest.get("skin") if base_manifest else None
        )

        try:
            final_manifest = await asyncio.wait_for(
                self.get_template_manifest(
                    component_path_base, skin=theme_to_use
                ),
                timeout=_TEMPLATE_RESOLVE_TIMEOUT,
            )
        except TimeoutError:
            logger.warning(
                f"解析组件 '{component_path_base}' 主题清单超时"
            )
            final_manifest = None

        entrypoint_filename = (
            final_manifest.get("entrypoint", "main.html")
            if final_manifest
            else "main.html"
        )

        potential_paths: list[str] = []
        base = PurePosixPath(component_path_base)

        if theme_to_use and theme_to_use != "default":
            potential_paths.append(
                str(base / theme_to_use / entrypoint_filename)
            )
            potential_paths.append(
                str(base / "skins" / theme_to_use / entrypoint_filename)
            )

        potential_paths.append(
            str(base / "default" / entrypoint_filename)
        )
        potential_paths.append(
            str(base / entrypoint_filename)
        )

        if entrypoint_filename == "main.html":
            potential_paths.append(f"{component_path_base}.html")

        for path in potential_paths:
            try:
                self.jinja_env.get_template(path)
                context.resolved_template_paths[cache_key] = path
                return path
            except TemplateNotFound:
                continue

        err_msg = (
            f"无法为组件 '{component_path_base}' 找到任何可用的模板。"
            f"检查路径: {potential_paths}"
        )
        logger.error(err_msg)
        raise TemplateNotFound(err_msg)

    async def _load_single_manifest(
        self, path_str: str
    ) -> dict[str, Any] | None:
        """从指定路径加载单个 manifest.json 文件。"""
        normalized_path = path_str.replace("\\", "/")
        manifest_path_str = f"{normalized_path}/manifest.json"

        if not self.jinja_env.loader:
            return None

        try:
            source, filepath, _ = self.jinja_env.loader.get_source(
                self.jinja_env, manifest_path_str
            )
            logger.debug(
                f"找到清单文件: '{manifest_path_str}' "
                f"(从 '{filepath}' 加载)"
            )
            return json.loads(source)
        except TemplateNotFound:
            return None
        except json.JSONDecodeError:
            logger.warning(f"清单文件 '{manifest_path_str}' 解析失败")
            return None

    async def _load_theme_config(
        self, path_str: str
    ) -> dict[str, Any] | None:
        """从指定路径加载 theme.json 文件。"""
        normalized_path = path_str.replace("\\", "/")
        theme_path_str = f"{normalized_path}/theme.json"

        if not self.jinja_env.loader:
            return None

        try:
            source, filepath, _ = self.jinja_env.loader.get_source(
                self.jinja_env, theme_path_str
            )
            logger.debug(
                f"找到主题配置: '{theme_path_str}' "
                f"(从 '{filepath}' 加载)"
            )
            return json.loads(source)
        except TemplateNotFound:
            return None
        except json.JSONDecodeError:
            logger.warning(f"主题配置 '{theme_path_str}' 解析失败")
            return None

    async def _load_and_merge_manifests(
        self,
        component_path: Path | str,
        skin: str | None = None,
    ) -> dict[str, Any] | None:
        """加载主题配置文件 theme.json。"""
        theme_config: dict[str, Any] | None = None
        base = PurePosixPath(component_path)

        if skin and skin != "default":
            theme_config = await self._load_theme_config(
                str(base / skin)
            )
            if not theme_config:
                theme_config = await self._load_theme_config(
                    str(base / "skins" / skin)
                )

        if not theme_config:
            theme_config = await self._load_theme_config(
                str(base / "default")
            )

        return theme_config

    async def get_template_manifest(
        self, component_path: str, skin: str | None = None
    ) -> dict[str, Any] | None:
        """查找并解析组件的 manifest.json 文件，支持缓存。"""
        cache_key = f"{component_path}:{skin or 'base'}"

        if cache_key in self._manifest_cache:
            return self._manifest_cache[cache_key]

        async with self._manifest_cache_lock:
            if cache_key in self._manifest_cache:
                return self._manifest_cache[cache_key]

            manifest = await self._load_and_merge_manifests(
                component_path, skin
            )
            self._manifest_cache[cache_key] = manifest
            return manifest

    def tpl_render_opts(
        self, manifest: dict[str, Any] | None, template_name: str
    ) -> dict[str, Any]:
        """获取特定模板的渲染选项。"""
        if not manifest:
            return {}

        result = manifest.get("render_options", {}).copy()
        template_options = manifest.get("template_render_options", [])

        if isinstance(template_options, list):
            for item in template_options:
                if item.get("template") == template_name:
                    specific_options = item.get("render_options", {})
                    if isinstance(specific_options, dict):
                        result = deep_merge_dict(result, specific_options)
                    break

        return result

    async def resolve_markdown_style_path(
        self, style_name: str, context: "RenderContext"
    ) -> Path | None:
        """按照注册->主题约定->默认约定的顺序解析 Markdown 样式路径。"""
        if cached_path := context.resolved_style_paths.get(style_name):
            return cached_path

        resolved_path: Path | None = None
        if registered_path := asset_registry.resolve_markdown_style(
            style_name
        ):
            resolved_path = registered_path

        elif self.current_theme:
            theme_style_path = (
                self.current_theme.assets_dir
                / "css"
                / "styles"
                / "markdown"
                / f"{style_name}.css"
            )
            if theme_style_path.exists():
                resolved_path = theme_style_path

            if not resolved_path:
                default_style_path = (
                    self.current_theme.default_assets_dir
                    / "css"
                    / "styles"
                    / "markdown"
                    / f"{style_name}.css"
                )
                if default_style_path.exists():
                    resolved_path = default_style_path

        if resolved_path:
            context.resolved_style_paths[style_name] = resolved_path
        else:
            logger.warning(
                f"Markdown 样式 '{style_name}' "
                f"在注册表和主题目录中均未找到。"
            )

        return resolved_path

    async def _render_component_to_html(
        self,
        context: "RenderContext",
        **kwargs,
    ) -> str:
        """将 Renderable 组件渲染成 HTML 字符串。"""
        component = context.component
        assert self.current_theme is not None

        data_dict = component.get_render_data()
        theme_context_dict = model_dump(self.current_theme)

        theme_name = self.current_theme.name
        if theme_name not in self._theme_css_cache:
            theme_css_template = self.jinja_env.get_template(
                "theme.css.jinja"
            )
            self._theme_css_cache[theme_name] = (
                await theme_css_template.render_async(
                    theme=theme_context_dict
                )
            )
        theme_css_content = self._theme_css_cache[theme_name]

        resolved_template_name = await self._resolve_component_template(
            component, context
        )
        template = self.jinja_env.get_template(resolved_template_name)

        unpacked_data = {}
        for key, value in data_dict.items():
            if key in RESERVED_TEMPLATE_KEYS:
                logger.warning(
                    f"模板数据键 '{key}' 与渲染器保留关键字冲突，"
                    f"在模板 '{component.template_name}' 中"
                    f"请使用 'data.{key}' 访问。"
                )
            else:
                unpacked_data[key] = value

        template_context = {
            "data": component,
            "theme": theme_context_dict,
            "frameless": kwargs.get("frameless", False),
        }
        template_context.update(unpacked_data)
        template_context.update(kwargs)

        html_fragment = await template.render_async(**template_context)

        if not kwargs.get("frameless", False):
            base_template = self.jinja_env.get_template(
                "partials/_base.html"
            )
            page_context = {
                "data": component,
                "theme_css": theme_css_content,
                "collected_inline_css": context.collected_inline_css,
                "required_scripts": list(context.collected_scripts),
                "collected_asset_styles": list(
                    context.collected_asset_styles
                ),
                "body_content": html_fragment,
            }
            return await base_template.render_async(**page_context)

        return html_fragment
