import asyncio
from collections.abc import Awaitable, Callable
import hashlib
import inspect
from pathlib import Path, PurePosixPath
from typing import ClassVar

import aiofiles
from jinja2 import (
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    PrefixLoader,
    TemplateNotFound,
    select_autoescape,
)
from nonebot.utils import is_coroutine_callable
import orjson as json

from liuying.configs.config import Config
from liuying.configs.path_config import THEMES_PATH, UI_CACHE_PATH
from liuying.services.cache import Cache
from liuying.services.log import logger
from liuying.utils.pydantic_compat import model_dump

from .config import RESERVED_TEMPLATE_KEYS
from .context import RenderContext
from .engine import get_screenshot_engine
from .protocols import Renderable, RenderResult, ScreenshotEngine
from .registry import asset_registry
from .theme import RelativePathEnvironment, ThemeManager
from .utils import deep_merge_dict, pydantic_tojson_filter, rewrite_urls

_TEMPLATE_RESOLVE_TIMEOUT = 10.0
_RENDER_CACHE_EXPIRE = 3600


class RendererService:
    """图片渲染服务的统一门面。

    作为UI渲染的中心枢纽，负责编排和调用底层服务，提供统一的渲染接口。
    """

    _plugin_template_paths: ClassVar[dict[str, Path]] = {}
    _render_cache: ClassVar[Cache[bytes]] = Cache(
        "UI_RENDER", result_type=bytes
    )

    def __init__(self):
        self._jinja_env: Environment | None = None
        self._theme_manager: ThemeManager | None = None
        self._screenshot_engine: ScreenshotEngine | None = None
        self._initialized = False
        self._init_lock = asyncio.Lock()
        self._custom_filters: dict[str, Callable] = {}
        self._custom_globals: dict[str, Callable] = {}

        self.filter("dump_json")(pydantic_tojson_filter)

    def _create_jinja_env(self) -> Environment:
        """创建并配置 Jinja2 渲染环境。"""
        prefix_loader = PrefixLoader(
            {
                namespace: FileSystemLoader(str(path.absolute()))
                for namespace, path in self._plugin_template_paths.items()
            }
        )
        theme_loader = FileSystemLoader(str(THEMES_PATH / "default"))
        final_loader = ChoiceLoader([prefix_loader, theme_loader])

        return RelativePathEnvironment(
            loader=final_loader,
            enable_async=True,
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def register_template_namespace(self, namespace: str, path: Path):
        """为插件注册一个Jinja2模板命名空间。"""
        if namespace in self._plugin_template_paths:
            logger.warning(
                f"模板命名空间 '{namespace}' 已被注册，将被覆盖。"
            )
        if not path.is_dir():
            raise ValueError(
                f"提供的路径 '{path}' 不是一个有效的目录。"
            )
        self._plugin_template_paths[namespace] = path

    def register_markdown_style(self, name: str, path: Path):
        """为 Markdown 渲染器注册一个具名样式（委托给 AssetRegistry）。"""
        if not path.is_file():
            raise ValueError(
                f"提供的路径 '{path}' 不是一个有效的 CSS 文件。"
            )
        asset_registry.register_markdown_style(name, path)

    def filter(self, name: str) -> Callable:
        """装饰器：注册一个自定义 Jinja2 过滤器。"""
        def decorator(func: Callable) -> Callable:
            if name in self._custom_filters:
                logger.warning(
                    f"Jinja2 过滤器 '{name}' 已被注册，将被覆盖。"
                )
            self._custom_filters[name] = func
            logger.debug(f"已注册自定义 Jinja2 过滤器: '{name}'")
            return func
        return decorator

    def global_function(self, name: str) -> Callable:
        """装饰器：注册一个自定义 Jinja2 全局函数。"""
        def decorator(func: Callable) -> Callable:
            if name in self._custom_globals:
                logger.warning(
                    f"Jinja2 全局函数 '{name}' 已被注册，将被覆盖。"
                )
            self._custom_globals[name] = func
            logger.debug(f"已注册自定义 Jinja2 全局函数: '{name}'")
            return func
        return decorator

    async def initialize(self):
        """延迟初始化方法，在 on_startup 钩子中调用。"""
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return

            self._jinja_env = self._create_jinja_env()
            self._jinja_env.filters.update(self._custom_filters)
            self._jinja_env.globals.update(self._custom_globals)
            self._screenshot_engine = get_screenshot_engine()
            self._theme_manager = ThemeManager(self._jinja_env)

            await self._theme_manager.load_theme("default")
            self._initialized = True

    async def _collect_dependencies_recursive(
        self, component: Renderable, context: RenderContext
    ):
        """递归遍历组件树，收集所有依赖项（CSS, JS, 额外CSS）并存入上下文。"""
        component_id = id(component)
        if component_id in context.processed_components:
            return
        context.processed_components.add(component_id)

        component_path_base = str(component.template_name)
        variant = getattr(component, "variant", None)
        try:
            manifest = await asyncio.wait_for(
                context.theme_manager.get_template_manifest(
                    component_path_base, skin=variant
                ),
                timeout=_TEMPLATE_RESOLVE_TIMEOUT,
            )
        except TimeoutError:
            logger.warning(
                f"收集组件 '{component_path_base}' 依赖超时，跳过"
            )
            manifest = None

        style_paths_to_load = await self._get_style_paths(
            manifest, component_path_base, context
        )

        for css_template_path in style_paths_to_load:
            try:
                css_template = (
                    context.theme_manager.jinja_env.get_template(
                        css_template_path
                    )
                )
                theme_context = {
                    "theme": context.theme_manager.jinja_env.globals.get(
                        "theme", {}
                    )
                }
                css_content = await css_template.render_async(
                    **theme_context
                )

                if (
                    hasattr(css_template, "filename")
                    and css_template.filename
                ):
                    css_content = rewrite_urls(
                        css_content,
                        Path(css_template.filename).parent,
                        is_css=True,
                    )

                context.collected_inline_css.append(css_content)
            except TemplateNotFound:
                pass

        context.collected_scripts.update(component.get_required_scripts())
        context.collected_asset_styles.update(component.get_required_styles())

        if hasattr(component, "get_extra_css"):
            res = component.get_extra_css(context)
            css_str = await res if inspect.isawaitable(res) else str(res)
            if css_str:
                context.collected_inline_css.append(css_str)

        for child in component.get_children():
            if child:
                await self._collect_dependencies_recursive(child, context)

    async def _get_style_paths(
        self,
        manifest: dict | None,
        component_path_base: str,
        context: RenderContext,
    ) -> list[str]:
        """获取需要加载的样式路径列表，支持扁平化主题目录回退。"""
        variant = getattr(context.component, "variant", None)
        style_paths: list[str] = []

        if manifest and "styles" in manifest:
            styles = (
                [manifest["styles"]]
                if isinstance(manifest["styles"], str)
                else manifest["styles"]
            )
            for style_path in styles:
                resolved = self._resolve_style_with_fallback(
                    component_path_base, style_path, variant, context
                )
                style_paths.append(resolved)
        else:
            resolved = self._resolve_style_with_fallback(
                component_path_base, "style.css", variant, context
            )
            style_paths.append(resolved)
        return style_paths

    def _resolve_style_with_fallback(
        self,
        component_path: str,
        style_file: str,
        variant: str | None,
        context: RenderContext,
    ) -> str:
        """按优先级解析样式路径，支持主题子目录回退。"""
        candidates: list[str] = []

        base = PurePosixPath(component_path)
        if variant and variant != "default":
            candidates.append(str(base / variant / style_file))
            candidates.append(str(base / "skins" / variant / style_file))

        candidates.append(str(base / "default" / style_file))
        candidates.append(str(base / style_file))

        for candidate in candidates:
            try:
                context.theme_manager.jinja_env.get_template(candidate)
                return candidate
            except TemplateNotFound:
                continue

        return candidates[-1]

    async def _render_component(
        self, context: RenderContext
    ) -> RenderResult:
        """核心的私有渲染方法，执行完整的渲染流程。"""
        return await self._apply_caching_layer(
            self._render_component_core, context
        )

    async def _apply_caching_layer(
        self,
        core_render_func: Callable[..., Awaitable[RenderResult]],
        context: RenderContext,
    ) -> RenderResult:
        """为核心渲染逻辑提供缓存层，使用流萤缓存系统支持LRU淘汰。"""
        component = context.component
        cache_path = None

        if Config.get_config("UI", "CACHE") and context.use_cache:
            try:
                template_name = component.template_name
                data_dict = component.get_render_data()
                resolved_data_dict = {
                    key: (
                        await value
                        if is_coroutine_callable(value)
                        else value
                    )
                    for key, value in data_dict.items()
                }
                variant = getattr(component, "variant", None) or "default"
                theme_name = (
                    context.theme_manager.current_theme.name
                    if context.theme_manager.current_theme
                    else "default"
                )
                cache_key_data = {
                    "tpl": template_name,
                    "theme": theme_name,
                    "variant": variant,
                    "data": resolved_data_dict,
                }
                data_bytes = json.dumps(
                    cache_key_data,
                    option=json.OPT_SORT_KEYS,
                )
                cache_key = hashlib.sha256(data_bytes).hexdigest()
                cache_path = UI_CACHE_PATH / f"{cache_key}.png"

                cached_bytes = await self._render_cache.get(cache_key)
                if cached_bytes is not None:
                    logger.debug(f"UI缓存命中: {cache_key[:16]}...")
                    return RenderResult(
                        image_bytes=cached_bytes,
                        html_content="<!-- from cache -->",
                    )

                if cache_path.exists():
                    async with aiofiles.open(cache_path, "rb") as f:
                        image_bytes = await f.read()
                    await self._render_cache.set(
                        cache_key,
                        image_bytes,
                        expire=_RENDER_CACHE_EXPIRE,
                    )
                    logger.debug(
                        f"UI文件缓存命中: {cache_key[:16]}..."
                    )
                    return RenderResult(
                        image_bytes=image_bytes,
                        html_content="<!-- from cache -->",
                    )

                logger.debug(f"UI缓存未命中: {cache_key[:16]}...")
            except Exception as e:
                logger.warning(f"UI缓存读取失败: {e}", e=e)
                cache_path = None

        result = await core_render_func(context)

        if (
            Config.get_config("UI", "CACHE")
            and context.use_cache
            and result.image_bytes
        ):
            try:
                await self._render_cache.set(
                    cache_key,
                    result.image_bytes,
                    expire=_RENDER_CACHE_EXPIRE,
                )
                if cache_path:
                    async with aiofiles.open(cache_path, "wb") as f:
                        await f.write(result.image_bytes)
                logger.debug(f"UI缓存写入成功: {cache_key[:16]}...")
            except Exception as e:
                logger.warning(f"UI缓存写入失败: {e}", e=e)

        return result

    async def _render_component_core(
        self, context: RenderContext
    ) -> RenderResult:
        """纯粹的核心渲染逻辑，不包含任何缓存处理。"""
        component = context.component

        try:
            if not self._initialized:
                await self.initialize()
            assert context.theme_manager is not None
            assert context.screenshot_engine is not None

            if self._is_standalone_template(component):
                return await self._render_standalone_template(context)

            return await self._render_theme_template(context)

        except Exception as e:
            logger.error(
                f"渲染组件 '{component.__class__.__name__}' 时发生错误",
                "RendererService",
                e=e,
            )
            raise RuntimeError(
                f"渲染组件 '{component.__class__.__name__}' 失败"
            ) from e

    def _is_standalone_template(self, component: Renderable) -> bool:
        """检查组件是否为独立模板。"""
        if not hasattr(component, "template_path"):
            return False
        template_path = getattr(component, "template_path")
        return isinstance(template_path, Path) and template_path.is_absolute()

    async def _render_standalone_template(
        self, context: RenderContext
    ) -> RenderResult:
        """渲染独立模板。"""
        component = context.component
        template_path = getattr(component, "template_path")

        await component.prepare()
        logger.debug(
            f"正在渲染独立模板: '{template_path}'", "RendererService"
        )

        template_dir = template_path.parent
        temp_loader = FileSystemLoader(str(template_dir))
        temp_env = Environment(
            loader=temp_loader,
            enable_async=True,
            autoescape=select_autoescape(["html", "xml"]),
        )

        temp_env.globals.update(context.theme_manager.jinja_env.globals)
        temp_env.filters.update(context.theme_manager.jinja_env.filters)
        temp_env.globals["asset"] = (
            context.theme_manager._create_standalone_asset_loader(
                template_dir
            )
        )
        temp_env.filters["md"] = context.theme_manager._markdown_filter

        data_dict = component.get_render_data()
        template = temp_env.get_template(template_path.name)

        template_context = {
            "theme": context.theme_manager.jinja_env.globals.get(
                "theme", {}
            ),
            "data": data_dict,
        }
        for key, value in data_dict.items():
            if key in RESERVED_TEMPLATE_KEYS:
                logger.warning(
                    f"模板数据键 '{key}' 与渲染器保留关键字冲突，"
                    f"在模板 '{component.template_name}' 中请使用 "
                    f"'data.{key}' 访问。"
                )
            else:
                template_context[key] = value
        html_content = await template.render_async(**template_context)

        html_content = rewrite_urls(html_content, template_path.parent)

        component_render_options = data_dict.get("render_options", {})
        if not isinstance(component_render_options, dict):
            component_render_options = {}

        final_render_options = component_render_options.copy()
        final_render_options.update(context.render_options)

        image_bytes = await context.screenshot_engine.render(
            html=html_content,
            base_url_path=template_dir,
            **final_render_options,
        )

        return RenderResult(
            image_bytes=image_bytes, html_content=html_content
        )

    async def _render_theme_template(
        self, context: RenderContext
    ) -> RenderResult:
        """渲染主题模板。"""
        component = context.component

        await component.prepare()
        await self._collect_dependencies_recursive(component, context)

        data_dict = component.get_render_data()
        component_render_options = data_dict.get("render_options", {})
        if not isinstance(component_render_options, dict):
            component_render_options = {}

        manifest = None
        variant = getattr(component, "variant", None)
        try:
            manifest = await asyncio.wait_for(
                context.theme_manager.get_template_manifest(
                    component.template_name, skin=variant
                ),
                timeout=_TEMPLATE_RESOLVE_TIMEOUT,
            )
        except TimeoutError:
            logger.warning(
                f"渲染主题模板时获取清单超时: "
                f"{component.template_name}"
            )

        try:
            resolved_template_name = await asyncio.wait_for(
                context.theme_manager._resolve_component_template(
                    component, context
                ),
                timeout=_TEMPLATE_RESOLVE_TIMEOUT,
            )
        except TimeoutError:
            raise RuntimeError(
                f"解析组件 '{component.template_name}' "
                f"模板路径超时"
            )

        template_filename = Path(resolved_template_name).name
        template_specific_options = (
            context.theme_manager.tpl_render_opts(
                manifest, template_filename
            )
        )

        final_render_options = template_specific_options.copy()
        final_render_options = deep_merge_dict(
            final_render_options, component_render_options
        )
        final_render_options = deep_merge_dict(
            final_render_options, context.render_options
        )

        if not context.theme_manager.current_theme:
            raise RuntimeError("渲染失败：主题未被正确加载。")

        html_content = (
            await context.theme_manager._render_component_to_html(
                context,
                **final_render_options,
            )
        )

        if context.theme_manager.jinja_env.loader:
            try:
                _, filepath, _ = (
                    context.theme_manager.jinja_env.loader.get_source(
                        context.theme_manager.jinja_env,
                        resolved_template_name,
                    )
                )
                if filepath:
                    html_content = rewrite_urls(
                        html_content, Path(filepath).parent
                    )
            except Exception:
                pass

        screenshot_options = final_render_options.copy()
        screenshot_options.pop("extra_css", None)
        screenshot_options.pop("frameless", None)

        image_bytes = await context.screenshot_engine.render(
            html=html_content,
            base_url_path=THEMES_PATH.parent,
            **screenshot_options,
        )

        return RenderResult(
            image_bytes=image_bytes, html_content=html_content
        )

    async def render(
        self,
        component: Renderable,
        use_cache: bool = False,
        **render_options,
    ) -> bytes:
        """统一的渲染入口，直接返回图片字节。

        参数:
            component: 可渲染的UI组件。
            use_cache: 是否启用渲染缓存，默认为 False。
            **render_options: 传递给截图引擎的额外参数。

        返回:
            bytes: 渲染后的PNG图片字节数据。
        """
        if not self._initialized:
            await self.initialize()
        assert self._theme_manager is not None
        assert self._screenshot_engine is not None

        return await self._do_render(component, use_cache, render_options)

    async def render_full_result(
        self,
        component: Renderable,
        use_cache: bool = False,
        **render_options,
    ) -> RenderResult:
        """渲染组件并返回包含图片和HTML的完整结果对象。

        参数:
            component: 可渲染的UI组件。
            use_cache: 是否启用渲染缓存，默认为 False。
            **render_options: 传递给截图引擎的额外参数。

        返回:
            RenderResult: 包含 image_bytes 和 html_content 的结果。
        """
        if not self._initialized:
            await self.initialize()
        assert self._theme_manager is not None
        assert self._screenshot_engine is not None

        context = RenderContext(
            renderer=self,
            theme_manager=self._theme_manager,
            screenshot_engine=self._screenshot_engine,
            component=component,
            use_cache=use_cache,
            render_options=render_options,
        )
        return await self._render_component(context)

    async def _do_render(
        self,
        component: Renderable,
        use_cache: bool,
        render_options: dict,
    ) -> bytes:
        """执行渲染核心逻辑。"""
        context = RenderContext(
            renderer=self,
            theme_manager=self._theme_manager,
            screenshot_engine=self._screenshot_engine,
            component=component,
            use_cache=use_cache,
            render_options=render_options,
        )
        result = await self._render_component(context)
        if Config.get_config("UI", "DEBUG_MODE") and result.html_content:
            logger.info(
                f"--- [UI DEBUG] HTML for "
                f"{component.__class__.__name__} ---\n"
                f"{result.html_content[:500]}...\n"
                f"--- [UI DEBUG] End of HTML ---"
            )
        if result.image_bytes is None:
            raise RuntimeError("渲染成功但未能生成图片字节数据。")
        return result.image_bytes

    async def render_to_html(
        self, component: Renderable, frameless: bool = False
    ) -> str:
        """调试方法：只执行到HTML生成步骤，不进行截图。"""
        if not self._initialized:
            await self.initialize()
        assert self._theme_manager is not None
        assert self._screenshot_engine is not None

        context = RenderContext(
            renderer=self,
            theme_manager=self._theme_manager,
            screenshot_engine=self._screenshot_engine,
            component=component,
            use_cache=False,
            render_options={"frameless": frameless},
        )
        await self._collect_dependencies_recursive(component, context)
        return await self._theme_manager._render_component_to_html(
            context, frameless=frameless
        )

    async def reload_theme(self) -> str:
        """重新加载当前主题的配置和样式，并清除缓存的Jinja环境。"""
        if not self._initialized:
            await self.initialize()
        assert self._theme_manager is not None

        self._theme_manager.clear_cache()
        await self._render_cache.clear()
        logger.debug("已清除UI清单缓存和渲染缓存。")
        await self._theme_manager.load_theme("default")
        logger.info("主题 'default' 已成功重载。")
        return "default"

    def list_available_themes(self) -> list[str]:
        """获取所有可用主题的列表。"""
        if not self._initialized or not self._theme_manager:
            raise RuntimeError("ThemeManager尚未初始化。")
        return self._theme_manager.list_available_themes()

    def list_page_themes(self, page_path: str) -> list[str]:
        """获取指定页面的可用主题列表。"""
        if not self._initialized or not self._theme_manager:
            raise RuntimeError("ThemeManager尚未初始化。")
        return self._theme_manager.list_page_themes(page_path)

    def get_theme_price(self, page_path: str, theme_name: str) -> int:
        """获取指定页面主题的价格。"""
        if not self._initialized or not self._theme_manager:
            return 0
        return self._theme_manager.get_theme_price(page_path, theme_name)

    def get_theme_label(self, page_path: str, theme_name: str) -> str:
        """获取指定页面主题的中文标签。"""
        if not self._initialized or not self._theme_manager:
            return theme_name
        return self._theme_manager.get_theme_label(page_path, theme_name)

    def resolve_theme_name(
        self, page_path: str, label_or_name: str
    ) -> str | None:
        """将中文标签或英文名称解析为主题目录名。"""
        if not self._initialized or not self._theme_manager:
            return None
        return self._theme_manager.resolve_theme_name(page_path, label_or_name)

    def resolve_feature_key(self, label_or_key: str) -> str | None:
        """将中文功能标签或英文功能键解析为功能键。"""
        if not self._initialized or not self._theme_manager:
            return None
        return self._theme_manager.resolve_feature_key(label_or_key)

    def get_store_items(self) -> list:
        """获取主题商店所有可购买的主题条目。"""
        if not self._initialized or not self._theme_manager:
            raise RuntimeError("ThemeManager尚未初始化。")
        return self._theme_manager.get_store_items()

    def discover_features(self) -> dict[str, dict[str, str]]:
        """自动扫描发现所有页面功能。"""
        if not self._initialized or not self._theme_manager:
            raise RuntimeError("ThemeManager尚未初始化。")
        return self._theme_manager.discover_features()

    async def resolve_user_variant(
        self, page_path: str, user_id: str
    ) -> str | None:
        """根据页面路径和用户ID自动解析用户的主题变体。"""
        if not self._initialized or not self._theme_manager:
            return None
        return await self._theme_manager.resolve_user_variant(
            page_path, user_id
        )

    async def render_html(
        self,
        html_content: str | Path,
        base_path: Path | None = None,
        *,
        use_cache: bool = False,
        apply_theme: bool = True,
        **render_options,
    ) -> bytes:
        """渲染纯 HTML 内容为图片。

        参数:
            html_content: HTML 字符串或 HTML 文件路径。
            base_path: 用于解析相对路径的基础目录。
            use_cache: 是否启用缓存，默认为 False。
            apply_theme: 是否应用主题框架，默认为 True。
            **render_options: 传递给截图引擎的额外参数。

        返回:
            bytes: 渲染后的 PNG 图片字节数据。
        """
        if not self._initialized:
            await self.initialize()
        assert self._screenshot_engine is not None

        if isinstance(html_content, Path):
            base_path = base_path or html_content.parent
            html_content = html_content.read_text(encoding="utf-8")

        final_base_path = base_path or Path.cwd()
        final_html = html_content

        if apply_theme and self._theme_manager:
            final_html = await self._wrap_html_with_theme(html_content)

        if use_cache:
            return await self._render_html_with_cache(
                final_html, final_base_path, render_options
            )

        return await self._screenshot_engine.render(
            html=final_html,
            base_url_path=final_base_path,
            **render_options,
        )

    async def _wrap_html_with_theme(self, html_content: str) -> str:
        """将 HTML 内容包装到主题框架中，添加主题样式和基础结构。"""
        if not self._theme_manager or not self._theme_manager.current_theme:
            return html_content

        try:
            theme_css_template = self._jinja_env.get_template(
                "theme.css.jinja"
            )
            theme_context_dict = model_dump(
                self._theme_manager.current_theme
            )
            theme_css = await theme_css_template.render_async(
                theme=theme_context_dict
            )
        except Exception as e:
            logger.warning(f"生成主题 CSS 失败: {e}")
            theme_css = ""

        return (
            f'<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n'
            f'    <meta charset="UTF-8">\n'
            f'    <meta name="viewport" content='
            f'"width=device-width, initial-scale=1.0">\n'
            f"    <style>{theme_css}</style>\n"
            f"</head>\n<body>\n{html_content}\n</body>\n</html>"
        )

    async def _render_html_with_cache(
        self, html_content: str, base_path: Path, render_options: dict
    ) -> bytes:
        """带缓存的 HTML 渲染，使用流萤缓存系统。"""
        cache_key = hashlib.sha256(html_content.encode()).hexdigest()

        if Config.get_config("UI", "CACHE"):
            cached_bytes = await self._render_cache.get(
                f"html_{cache_key}"
            )
            if cached_bytes is not None:
                logger.debug(f"HTML缓存命中: {cache_key[:16]}...")
                return cached_bytes

        image_bytes = await self._screenshot_engine.render(
            html=html_content,
            base_url_path=base_path,
            **render_options,
        )

        if Config.get_config("UI", "CACHE") and image_bytes:
            try:
                await self._render_cache.set(
                    f"html_{cache_key}",
                    image_bytes,
                    expire=_RENDER_CACHE_EXPIRE,
                )
                logger.debug(
                    f"HTML缓存写入成功: {cache_key[:16]}..."
                )
            except Exception as e:
                logger.warning(f"HTML缓存写入失败: {e}")

        return image_bytes
