"""主题管理器：主题加载、模板解析与组件 HTML 组装。"""

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
import markdown as markdown_lib
from markupsafe import Markup
from orjson import JSONDecodeError
from orjson import loads as json_loads
from pydantic import BaseModel

from liuying.configs.path_config import THEMES_PATH
from liuying.services.log import logger
from liuying.services.renderer.config import RESERVED_TEMPLATE_KEYS
from liuying.services.renderer.protocols import Renderable
from liuying.services.renderer.registry import asset_registry
from liuying.services.renderer.resolver import ResourceResolver
from liuying.services.renderer.store import (
    ThemeCatalog,
    ThemeStoreItem,
    has_template_suffix,
)
from liuying.utils.pydantic_compat import model_dump

if TYPE_CHECKING:
    from .context import RenderContext

from .config import RESOLVE_TIMEOUT
from .utils import deep_merge_dict

# Markdown 转 HTML 使用的扩展集合
_MD_EXTENSIONS = [
    "pymdownx.tasklist",
    "tables",
    "fenced_code",
    "codehilite",
    "mdx_math",
    "pymdownx.tilde",
]


class RelativePathEnvironment(Environment):
    """支持模板间相对路径引用的 Jinja2 环境。"""

    def join_path(self, template: str, parent: str) -> str:
        """解析模板间的相对引用路径。

        参数:
            template: 被引用的模板名（可能以 ./ 或 ../ 开头）。
            parent: 发起引用的父模板名。

        返回:
            str: 相对父模板目录解析后的模板名。
        """
        if template.startswith(("./", "../")):
            return str(PurePosixPath(parent).parent / template)
        return super().join_path(template, parent)


class Theme(BaseModel):
    """已加载主题的数据模型。"""

    name: str
    """主题名称"""
    palette: dict[str, Any]
    """调色板数据（mode/colors/component_colors）"""
    style_css: str = ""
    """主题附加样式（预留）"""
    assets_dir: Path
    """当前主题的 assets 目录"""
    default_assets_dir: Path
    """默认主题的 assets 目录"""

    @property
    def root(self) -> Path:
        """返回当前主题根目录（含 pages/ 与 components/）。

        返回:
            Path: 主题根目录。
        """
        return self.assets_dir.parent

    @property
    def default_root(self) -> Path:
        """返回默认主题根目录。

        返回:
            Path: 默认主题的根目录。
        """
        return self.default_assets_dir.parent


def markdown_filter(text: str) -> str:
    """Jinja2 过滤器：将 Markdown 文本转换为 HTML。

    参数:
        text: Markdown 源文本，非字符串时返回空串。

    返回:
        str: 转换后的 HTML 片段。
    """
    if not isinstance(text, str):
        return ""
    return markdown_lib.markdown(
        text,
        extensions=_MD_EXTENSIONS,
        extension_configs={"mdx_math": {"enable_dollar_delimiter": True}},
    )


class ThemeManager:
    """主题管理器，负责主题加载、模板解析与组件到 HTML 的渲染。"""

    def __init__(self, env: Environment) -> None:
        """初始化管理器并注册模板全局函数与过滤器。

        参数:
            env: 已构建的 Jinja2 异步环境。
        """
        self.jinja_env = env
        self.current_theme: Theme | None = None
        self.catalog = ThemeCatalog()

        self.jinja_env.globals["render"] = self._render_child_global
        self.jinja_env.globals["asset"] = self._make_asset_loader()
        self.jinja_env.globals["resolve_template"] = (
            self.resolve_component_template
        )
        self.jinja_env.filters["md"] = markdown_filter

        self._manifest_cache: dict[str, dict[str, Any] | None] = {}
        self._manifest_lock = asyncio.Lock()
        self._theme_css_cache: dict[str, str] = {}
        self._template_cache: dict[str, str] = {}

    # ---------- 主题加载 ----------

    def list_available_themes(self) -> list[str]:
        """扫描主题目录，返回全部可用的全局主题名称。

        返回:
            list[str]: 含 palette.json 的主题目录名列表。
        """
        if not THEMES_PATH.is_dir():
            return []
        return [
            d.name
            for d in THEMES_PATH.iterdir()
            if d.is_dir() and (d / "palette.json").exists()
        ]

    async def load_theme(self, theme_name: str = "default") -> None:
        """加载指定全局主题，并注入模板全局变量。

        目标主题不存在时回退加载 default；同时把 default 主题的调色板
        作为 default_theme_palette 全局变量供变量生成器做映射回退。

        参数:
            theme_name: 主题目录名，默认加载 "default"。

        异常:
            FileNotFoundError: 默认主题 default 也未找到时抛出。
        """
        theme_dir = THEMES_PATH / theme_name
        if not theme_dir.is_dir():
            logger.error(f"主题 '{theme_name}' 不存在，将回退到默认主题。")
            if theme_name == "default":
                raise FileNotFoundError("默认主题 'default' 未找到！")
            theme_name = "default"
            theme_dir = THEMES_PATH / "default"

        self._sync_theme_loader(theme_dir)
        default_palette = (
            self._read_json(THEMES_PATH / "default" / "palette.json") or {}
        )
        self.current_theme = Theme(
            name=theme_name,
            palette=self._read_json(theme_dir / "palette.json") or {},
            assets_dir=theme_dir / "assets",
            default_assets_dir=THEMES_PATH / "default" / "assets",
        )
        self.jinja_env.globals["theme"] = model_dump(self.current_theme)
        self.jinja_env.globals["default_theme_palette"] = default_palette
        logger.info(f"主题管理器已加载主题: {theme_name}")

    def _sync_theme_loader(self, theme_dir: Path) -> None:
        """把主题目录与默认主题目录挂到模板加载链最前端。

        参数:
            theme_dir: 待加载的主题根目录。
        """
        loader = self.jinja_env.loader
        if not (loader and isinstance(loader, ChoiceLoader)):
            return
        loaders = list(loader.loaders)
        if len(loaders) > 1 and isinstance(loaders[0], PrefixLoader):
            default_dir = str(THEMES_PATH / "default")
            loaders[1] = FileSystemLoader([str(theme_dir), default_dir])
            loader.loaders = loaders

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        """读取 JSON 文件。

        参数:
            path: JSON 文件路径。

        返回:
            dict[str, Any] | None: 解析结果，文件缺失或解析失败时返回 None。
        """
        if not path.exists():
            return None
        try:
            return json_loads(path.read_bytes())
        except (JSONDecodeError, OSError):
            logger.warning(f"JSON 文件解析失败: '{path}'")
            return None

    def clear_cache(self) -> None:
        """清空清单、主题 CSS、模板解析与商店缓存。"""
        self._manifest_cache.clear()
        self._theme_css_cache.clear()
        self._template_cache.clear()
        self.catalog.clear_cache()
        logger.debug("主题管理器缓存已全部清除")

    # ---------- 页面主题 / 商店（委托 ThemeCatalog） ----------

    def _roots(self) -> tuple[Path, Path] | None:
        """返回当前主题根目录与默认主题根目录。

        返回:
            tuple[Path, Path] | None: (当前主题根, 默认主题根)，
                主题未加载时返回 None。
        """
        if not self.current_theme:
            return None
        return self.current_theme.root, self.current_theme.default_root

    def list_page_themes(self, page_path: str) -> list[str]:
        """列出指定页面可用的页面级主题。

        参数:
            page_path: 页面路径，如 "pages/builtin/signIn"。

        返回:
            list[str]: 主题目录名列表，未加载主题时返回 ["default"]。
        """
        if roots := self._roots():
            return self.catalog.list_page_themes(roots[0], page_path)
        return ["default"]

    def get_theme_price(self, page_path: str, theme_name: str) -> int:
        """查询页面主题价格。

        参数:
            page_path: 页面路径。
            theme_name: 主题目录名。

        返回:
            int: 主题价格，默认主题或未配置时返回 0。
        """
        if roots := self._roots():
            return self.catalog.get_theme_price(
                roots[0], roots[1], page_path, theme_name
            )
        return 0

    def get_theme_label(self, page_path: str, theme_name: str) -> str:
        """查询页面主题的中文标签。

        参数:
            page_path: 页面路径。
            theme_name: 主题目录名。

        返回:
            str: 中文标签，未配置时返回主题目录名。
        """
        if roots := self._roots():
            return self.catalog.get_theme_label(
                roots[0], roots[1], page_path, theme_name
            )
        return theme_name

    def resolve_theme_name(
        self, page_path: str, label_or_name: str
    ) -> str | None:
        """把中文标签或英文目录名解析为主题目录名。

        参数:
            page_path: 页面路径。
            label_or_name: 中文标签（如"粉色"）或英文目录名（如"pink"）。

        返回:
            str | None: 匹配的主题目录名，未匹配时返回 None。
        """
        if roots := self._roots():
            return self.catalog.resolve_theme_name(
                roots[0], roots[1], page_path, label_or_name
            )
        return None

    def discover_features(self) -> dict[str, dict[str, str]]:
        """自动发现全部内置页面功能。

        返回:
            dict[str, dict[str, str]]: 功能键到 {page_path, label} 的映射，
                主题未加载时返回空字典。
        """
        if roots := self._roots():
            return self.catalog.discover_features(roots[0])
        return {}

    def resolve_feature_key(self, label_or_key: str) -> str | None:
        """把中文功能标签或英文功能键解析为功能键。

        参数:
            label_or_key: 中文标签（如"签到"）或英文键（如"sign"）。

        返回:
            str | None: 匹配的功能键，未匹配时返回 None。
        """
        if roots := self._roots():
            return self.catalog.resolve_feature_key(roots[0], label_or_key)
        return None

    def get_store_items(self) -> list[ThemeStoreItem]:
        """获取主题商店全部条目。

        返回:
            list[ThemeStoreItem]: 商店条目列表，主题未加载时返回空列表。
        """
        if roots := self._roots():
            return self.catalog.get_store_items(roots[0], roots[1])
        return []

    async def resolve_user_variant(
        self, page_path: str, user_id: str
    ) -> str | None:
        """根据页面路径与用户 ID 解析用户的主题偏好。

        读取页面 manifest.json 的 feature 键，再查询用户主题表中
        该用户在此功能上选择的主题。

        参数:
            page_path: 页面路径，如 "pages/builtin/signIn"。
            user_id: 用户 ID。

        返回:
            str | None: 用户选择的主题名；默认主题、页面无 feature
                配置或主题未加载时返回 None。
        """
        if not self.current_theme:
            return None
        manifest = self._read_json(
            self.current_theme.root / page_path / "manifest.json"
        )
        if not (feature := (manifest or {}).get("feature")):
            return None

        from liuying.models._user.user_theme import UserTheme

        current = await UserTheme.get_current_theme(user_id, feature)
        return None if current == "default" else current

    # ---------- 模板与清单解析 ----------

    async def get_component_manifest(self, component_path: str) -> dict | None:
        """获取组件目录的 manifest.json。

        清单包含 entrypoint、styles、render_options、skin 等配置，
        结果带缓存与并发保护。

        参数:
            component_path: 组件模板路径，如 "components/core/card"。

        返回:
            dict | None: 清单字典，文件缺失或解析失败时返回 None。
        """
        if component_path in self._manifest_cache:
            return self._manifest_cache[component_path]

        async with self._manifest_lock:
            if component_path not in self._manifest_cache:
                self._manifest_cache[component_path] = await asyncio.wait_for(
                    self._load_manifest_file(component_path),
                    timeout=RESOLVE_TIMEOUT,
                )
            return self._manifest_cache[component_path]

    async def _load_manifest_file(self, component_path: str) -> dict | None:
        """从模板加载器读取组件根目录的 manifest.json。

        参数:
            component_path: 组件模板路径。

        返回:
            dict | None: 清单字典，文件缺失或解析失败时返回 None。
        """
        loader = self.jinja_env.loader
        if not loader:
            return None
        manifest_path = f"{component_path}/manifest.json".replace("\\", "/")
        try:
            source, _filepath, _uptodate = loader.get_source(
                self.jinja_env, manifest_path
            )
        except TemplateNotFound:
            return None
        try:
            return json_loads(source.encode())
        except (JSONDecodeError, OSError):
            logger.warning(f"组件清单解析失败: '{manifest_path}'")
            return None

    async def _safe_component_manifest(
        self, component_path: str
    ) -> dict[str, Any] | None:
        """获取组件清单，超时降级为 None 并告警。

        参数:
            component_path: 组件模板路径。

        返回:
            dict[str, Any] | None: 组件清单，超时时返回 None。
        """
        try:
            return await asyncio.wait_for(
                self.get_component_manifest(component_path),
                timeout=RESOLVE_TIMEOUT,
            )
        except TimeoutError:
            logger.warning(f"解析组件 '{component_path}' 清单超时")
            return None

    async def get_template_manifest(
        self, component_path: str, skin: str | None = None
    ) -> dict[str, Any] | None:
        """获取组件的页面主题配置（theme.json），带缓存与并发保护。

        参数:
            component_path: 组件模板路径。
            skin: 页面主题名，None 时只查找 default 子目录。

        返回:
            dict[str, Any] | None: 主题配置字典，缺失或解析失败时返回 None。
        """
        cache_key = f"{component_path}:{skin or 'base'}"
        if cache_key in self._manifest_cache:
            return self._manifest_cache[cache_key]

        async with self._manifest_lock:
            if cache_key not in self._manifest_cache:
                self._manifest_cache[cache_key] = await asyncio.wait_for(
                    self._load_theme_config(component_path, skin),
                    timeout=RESOLVE_TIMEOUT,
                )
            return self._manifest_cache[cache_key]

    async def _load_theme_config(
        self, component_path: str, skin: str | None
    ) -> dict[str, Any] | None:
        """按 变体目录 -> skins 目录 -> default 目录 的顺序加载 theme.json。

        参数:
            component_path: 组件模板路径。
            skin: 页面主题名。

        返回:
            dict[str, Any] | None: 主题配置字典，全部缺失时返回 None。
        """
        base = PurePosixPath(component_path)
        candidates: list[str] = []
        if skin and skin != "default":
            candidates.extend([str(base / skin), str(base / "skins" / skin)])
        candidates.append(str(base / "default"))

        for candidate in candidates:
            theme_path = f"{candidate}/theme.json".replace("\\", "/")
            if not self.jinja_env.loader:
                return None
            try:
                source, _filepath, _uptodate = self.jinja_env.loader.get_source(
                    self.jinja_env, theme_path
                )
            except TemplateNotFound:
                continue
            try:
                return json_loads(source.encode())
            except (JSONDecodeError, OSError):
                logger.warning(f"主题配置解析失败: '{theme_path}'")
        return None

    def tpl_render_opts(
        self, manifest: dict[str, Any] | None, template_name: str
    ) -> dict[str, Any]:
        """读取清单中的渲染选项，并与特定模板的选项合并。

        参数:
            manifest: 组件清单或页面主题配置。
            template_name: 入口模板文件名，用于匹配 template_render_options。

        返回:
            dict[str, Any]: 合并后的渲染选项，清单为空时返回空字典。
        """
        if not manifest:
            return {}
        result = dict(manifest.get("render_options", {}))
        for item in manifest.get("template_render_options", []) or []:
            if item.get("template") == template_name:
                if specific := item.get("render_options"):
                    if isinstance(specific, dict):
                        result = deep_merge_dict(result, specific)
                break
        return result

    async def resolve_component_template(
        self, component: Renderable, context: "RenderContext"
    ) -> str:
        """解析组件的实际模板路径，支持变体与 default 目录回退。

        按优先级尝试：变体目录 -> skins/变体目录 -> default 目录 ->
        组件根目录 -> 组件路径.html。

        参数:
            component: 待渲染的组件。
            context: 渲染上下文，解析结果会写入其路径缓存。

        返回:
            str: 实际可渲染的模板路径。

        异常:
            TemplateNotFound: 所有候选路径均不存在时抛出。
        """
        component_path = str(component.template_name)
        variant = getattr(component, "variant", None)
        cache_key = f"{component_path}::{variant or 'default'}"
        if cached := context.resolved_template_paths.get(cache_key):
            return cached

        # 已经是具体文件路径的组件直接校验存在性
        if has_template_suffix(component_path):
            self.jinja_env.get_template(component_path)
            return component_path

        manifest = await self._safe_component_manifest(component_path)
        entrypoint = (
            manifest.get("entrypoint", "main.html") if manifest else "main.html"
        )
        skin = variant or (manifest.get("skin") if manifest else None)

        base = PurePosixPath(component_path)
        candidates: list[str] = []
        if skin and skin != "default":
            candidates.append(str(base / skin / entrypoint))
            candidates.append(str(base / "skins" / skin / entrypoint))
        candidates.append(str(base / "default" / entrypoint))
        candidates.append(str(base / entrypoint))
        if entrypoint == "main.html":
            candidates.append(f"{component_path}.html")

        for candidate in candidates:
            try:
                self.jinja_env.get_template(candidate)
            except TemplateNotFound:
                continue
            context.resolved_template_paths[cache_key] = candidate
            return candidate

        raise TemplateNotFound(
            f"无法为组件 '{component_path}' 找到可用的模板，已尝试: {candidates}"
        )

    async def get_render_options(
        self, component_path: str, variant: str | None, template_name: str
    ) -> dict[str, Any]:
        """合并组件 manifest.json 与页面 theme.json 的渲染选项。

        参数:
            component_path: 组件模板路径。
            variant: 组件的变体名称。
            template_name: 入口模板文件名。

        返回:
            dict[str, Any]: 按 manifest -> theme.json 顺序深度合并的选项。
        """
        options: dict[str, Any] = {}
        if manifest := await self._safe_component_manifest(component_path):
            options = self.tpl_render_opts(manifest, template_name)
        if theme_config := await self._safe_theme_config(component_path, variant):
            options = deep_merge_dict(
                options, self.tpl_render_opts(theme_config, template_name)
            )
        return options

    async def _safe_theme_config(
        self, component_path: str, variant: str | None
    ) -> dict[str, Any] | None:
        """获取页面主题配置，超时降级为 None 并告警。

        参数:
            component_path: 组件模板路径。
            variant: 组件的变体名称。

        返回:
            dict[str, Any] | None: 主题配置，超时时返回 None。
        """
        try:
            return await asyncio.wait_for(
                self.get_template_manifest(component_path, skin=variant),
                timeout=RESOLVE_TIMEOUT,
            )
        except TimeoutError:
            logger.warning(f"解析组件 '{component_path}' 主题配置超时")
            return None

    # ---------- 资源加载器 ----------

    def _make_asset_loader(self) -> Callable[..., str]:
        """创建模板内使用的 asset() 全局函数。

        返回:
            Callable[..., str]: 带上下文的资源解析函数。
        """
        resolver = ResourceResolver(self)

        @pass_context
        def asset_loader(ctx: Any, asset_path: str) -> str:
            """把模板内的资源引用解析为绝对 URI。

            参数:
                ctx: Jinja2 渲染上下文。
                asset_path: 资源引用路径。

            返回:
                str: 资源的绝对 URI，未找到时返回空字符串。
            """
            template_name = ctx.name or "unknown_template"
            if not ctx.name:
                logger.warning("Jinja2 上下文缺少模板名称，无法解析资源。")
            return resolver.resolve_asset_uri(asset_path, template_name)

        return asset_loader

    def make_standalone_asset_loader(
        self, local_base_path: Path
    ) -> Callable[[str], str]:
        """为独立模板创建基于本地目录的资源加载器。

        参数:
            local_base_path: 独立模板所在目录，作为相对资源的基础路径。

        返回:
            Callable[[str], str]: 资源路径到绝对 URI 的解析函数。
        """

        def asset_loader(asset_path: str) -> str:
            """解析独立模板的资源引用。

            参数:
                asset_path: 资源引用路径，绝对路径直接使用。

            返回:
                str: 资源的绝对 URI，文件不存在时返回空字符串。
            """
            path = (
                Path(asset_path)
                if Path(asset_path).is_absolute()
                else (local_base_path / asset_path).resolve()
            )
            return path.as_uri() if path.exists() else ""

        return asset_loader

    # ---------- Markdown 样式 ----------

    async def resolve_markdown_style_path(
        self, style_name: str, context: "RenderContext"
    ) -> Path | None:
        """按 注册表 -> 当前主题 -> 默认主题 的顺序解析样式路径。

        参数:
            style_name: 样式名称。
            context: 渲染上下文，解析结果会写入其样式缓存。

        返回:
            Path | None: 样式文件路径，全部未找到时返回 None。
        """
        if style_name in context.resolved_style_paths:
            return context.resolved_style_paths[style_name]

        resolved: Path | None = asset_registry.resolve_markdown_style(style_name)
        if not resolved and self.current_theme:
            candidates = [
                self.current_theme.assets_dir
                / "css" / "styles" / "markdown" / f"{style_name}.css",
                self.current_theme.default_assets_dir
                / "css" / "styles" / "markdown" / f"{style_name}.css",
            ]
            resolved = next((p for p in candidates if p.exists()), None)

        context.resolved_style_paths[style_name] = resolved
        if not resolved:
            logger.warning(f"Markdown 样式 '{style_name}' 未找到。")
        return resolved

    # ---------- 模板全局函数 ----------

    async def _render_child_global(self, component: Renderable | None) -> str:
        """Jinja2 全局函数 render()：在模板内部渲染子组件。

        以 frameless 片段模式渲染，失败时返回 HTML 注释占位不中断整页。

        参数:
            component: 待渲染的子组件，为 None 时返回空字符串。

        返回:
            str: 子组件的 HTML 片段（Markup 安全标记）。
        """
        if not component:
            return ""
        try:
            template_path = await self._resolve_template_without_context(component)
            template = self.jinja_env.get_template(template_path)
            template_context: dict[str, Any] = {
                "data": component,
                "frameless": True,
            }
            template_context.update(component.get_render_data())
            return Markup(await template.render_async(**template_context))
        except Exception as e:
            name = component.__class__.__name__
            logger.error(f"模板内渲染组件 '{name}' 失败", e=e)
            return f"<!-- 组件渲染失败 {name}: {e} -->"

    async def _resolve_template_without_context(
        self, component: Renderable
    ) -> str:
        """脱离渲染上下文解析组件模板路径（用于模板内嵌套渲染）。

        参数:
            component: 待渲染的组件。

        返回:
            str: 模板路径，全部候选缺失时回退到组件根入口路径。
        """
        component_path = str(component.template_name)
        if has_template_suffix(component_path):
            return component_path

        variant = getattr(component, "variant", None)
        manifest = await self._safe_component_manifest(component_path)
        entrypoint = (
            manifest.get("entrypoint", "main.html") if manifest else "main.html"
        )
        skin = variant or (manifest.get("skin") if manifest else None)
        base = PurePosixPath(component_path)
        candidates: list[str] = []
        if skin and skin != "default":
            candidates.append(str(base / skin / entrypoint))
        candidates.extend([
            str(base / "default" / entrypoint),
            str(base / entrypoint),
        ])
        for candidate in candidates:
            try:
                self.jinja_env.get_template(candidate)
                return candidate
            except TemplateNotFound:
                continue
        return str(base / entrypoint)

    # ---------- 组件渲染为 HTML ----------

    async def render_component_to_html(
        self, context: "RenderContext", **kwargs: Any
    ) -> str:
        """把组件渲染成完整页面 HTML 或片段。

        frameless 为 True 时仅返回组件片段；否则把片段包进
        partials/_base.html，并注入主题 CSS 与收集到的依赖。

        参数:
            context: 渲染上下文（含已收集的依赖）。
            **kwargs: 额外的模板上下文与渲染选项，frameless 控制包装行为。

        返回:
            str: 完整页面 HTML 或组件片段。

        异常:
            TemplateNotFound: 组件模板无法解析时抛出。
        """
        component = context.component
        assert self.current_theme is not None

        theme_context = model_dump(self.current_theme)
        template_path = await self.resolve_component_template(component, context)
        template = self.jinja_env.get_template(template_path)

        template_context: dict[str, Any] = {
            "data": component,
            "theme": theme_context,
            "frameless": kwargs.get("frameless", False),
        }
        template_context.update(self._unpack_render_data(component))
        template_context.update(kwargs)
        fragment = await template.render_async(**template_context)

        if kwargs.get("frameless", False):
            return fragment

        base_template = self.jinja_env.get_template("partials/_base.html")
        return await base_template.render_async(
            data=component,
            theme_css=await self._theme_css(),
            collected_inline_css=context.collected_inline_css,
            required_scripts=list(context.collected_scripts),
            collected_asset_styles=list(context.collected_asset_styles),
            body_content=fragment,
        )

    def _unpack_render_data(self, component: Renderable) -> dict[str, Any]:
        """展开组件渲染数据为模板上下文，保留键冲突时的告警。

        与渲染器保留键冲突的数据只能通过 data.<key> 访问。

        参数:
            component: 待渲染的组件。

        返回:
            dict[str, Any]: 展开后的模板上下文数据。
        """
        unpacked: dict[str, Any] = {}
        for key, value in component.get_render_data().items():
            if key in RESERVED_TEMPLATE_KEYS:
                logger.warning(
                    f"模板数据键 '{key}' 与渲染器保留键冲突，"
                    f"请通过 data.{key} 访问（组件: {component.template_name}）"
                )
            else:
                unpacked[key] = value
        return unpacked

    async def _theme_css(self) -> str:
        """渲染主题核心 CSS，按主题名缓存。

        返回:
            str: 由 theme.css.jinja 生成的完整主题样式。
        """
        assert self.current_theme is not None
        theme_name = self.current_theme.name
        if theme_name not in self._theme_css_cache:
            template = self.jinja_env.get_template("theme.css.jinja")
            self._theme_css_cache[theme_name] = await template.render_async(
                theme=model_dump(self.current_theme)
            )
        return self._theme_css_cache[theme_name]
