"""图片渲染服务的统一门面。

负责编排主题管理器、依赖收集器、缓存与截图引擎，
向业务层提供稳定的渲染入口。
"""

import asyncio
from collections.abc import Callable
import hashlib
from pathlib import Path
from typing import Any, ClassVar

from jinja2 import (
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    PrefixLoader,
    select_autoescape,
)
from nonebot.utils import is_coroutine_callable

from liuying.configs.config import Config
from liuying.configs.path_config import THEMES_PATH
from liuying.services.log import logger
from liuying.services.renderer.core.config import (
    CONFIG_MODULE,
    DEBUG_CONFIG_KEY,
    RESERVED_TEMPLATE_KEYS,
)
from liuying.services.renderer.core.context import RenderContext
from liuying.services.renderer.core.protocols import (
    Renderable,
    RenderResult,
    ScreenshotEngine,
)
from liuying.services.renderer.core.utils import (
    deep_merge_dict,
    pydantic_tojson_filter,
    rewrite_urls,
)
from liuying.services.renderer.render.cache import RenderCache, render_cache_key
from liuying.services.renderer.render.dependency import DependencyCollector
from liuying.services.renderer.render.engine import get_screenshot_engine
from liuying.services.renderer.theme.catalog import ThemeStoreItem
from liuying.services.renderer.theme.manager import (
    RelativePathEnvironment,
    ThemeManager,
    markdown_filter,
)
from liuying.services.renderer.theme.registry import asset_registry
from liuying.utils.pydantic_compat import model_dump

# 传递给截图引擎前需要剥离的选项（它们仅作用于 HTML 组装阶段）
_HTML_ONLY_OPTIONS = frozenset({"extra_css", "frameless"})


def _load_html_file(path: Path) -> tuple[Path, str]:
    """读取 HTML 文件。

    同步辅助函数，供协程调用以避免在事件循环内执行 pathlib 阻塞方法。

    参数:
        path: HTML 文件路径。

    返回:
        tuple[Path, str]: (文件所在目录, 文件文本内容)。
    """
    return path.parent, path.read_text(encoding="utf-8")


class RendererService:
    """渲染服务门面：环境构建、注册接口与渲染编排。"""

    _plugin_template_paths: ClassVar[dict[str, Path]] = {}

    def __init__(self) -> None:
        self._jinja_env: Environment | None = None
        self._theme_manager: ThemeManager | None = None
        self._screenshot_engine: ScreenshotEngine | None = None
        self._initialized = False
        self._init_lock = asyncio.Lock()
        self._custom_filters: dict[str, Callable[..., Any]] = {}
        self._custom_globals: dict[str, Callable[..., Any]] = {}
        self._render_cache = RenderCache()
        self.filter("dump_json")(pydantic_tojson_filter)

    # ---------- 注册接口 ----------

    def register_template_namespace(self, namespace: str, path: Path) -> None:
        """为插件注册一个 Jinja2 模板命名空间（@namespace/ 前缀访问）。"""
        if namespace in self._plugin_template_paths:
            logger.warning(f"模板命名空间 '{namespace}' 已被注册，将被覆盖。")
        if not path.is_dir():
            raise ValueError(f"提供的路径 '{path}' 不是一个有效的目录。")
        self._plugin_template_paths[namespace] = path
        self._sync_namespace_loader()

    def _sync_namespace_loader(self) -> None:
        """把插件命名空间同步进已构建的模板加载链。"""
        if not (self._jinja_env and self._jinja_env.loader):
            return
        loader = self._jinja_env.loader
        if not isinstance(loader, ChoiceLoader) or not loader.loaders:
            return
        if isinstance(loader.loaders[0], PrefixLoader):
            loader.loaders[0].mapping = {
                namespace: FileSystemLoader(str(path.absolute()))
                for namespace, path in self._plugin_template_paths.items()
            }

    def register_markdown_style(self, name: str, path: Path) -> None:
        """为 Markdown 渲染注册一个具名样式（委托给资源注册表）。

        参数:
            name: 样式的唯一名称。
            path: 样式 CSS 文件路径。

        异常:
            ValueError: path 不是有效文件时抛出。
        """
        if not path.is_file():
            raise ValueError(f"提供的路径 '{path}' 不是一个有效的 CSS 文件。")
        asset_registry.register_markdown_style(name, path)

    def filter(self, name: str) -> Callable[[Callable], Callable]:
        """装饰器：注册自定义 Jinja2 过滤器。"""

        def decorator(func: Callable) -> Callable:
            if name in self._custom_filters:
                logger.warning(f"Jinja2 过滤器 '{name}' 已被注册，将被覆盖。")
            self._custom_filters[name] = func
            logger.debug(f"已注册自定义 Jinja2 过滤器: '{name}'")
            return func

        return decorator

    def global_function(self, name: str) -> Callable[[Callable], Callable]:
        """装饰器：注册自定义 Jinja2 全局函数。"""

        def decorator(func: Callable) -> Callable:
            if name in self._custom_globals:
                logger.warning(f"Jinja2 全局函数 '{name}' 已被注册，将被覆盖。")
            self._custom_globals[name] = func
            logger.debug(f"已注册自定义 Jinja2 全局函数: '{name}'")
            return func

        return decorator

    # ---------- 初始化 ----------

    def _build_jinja_env(self) -> Environment:
        """构建 Jinja2 环境：插件命名空间 + 主题目录。"""
        namespace_loader = PrefixLoader({
            namespace: FileSystemLoader(str(path.absolute()))
            for namespace, path in self._plugin_template_paths.items()
        })
        theme_loader = FileSystemLoader(str(THEMES_PATH / "default"))
        return RelativePathEnvironment(
            loader=ChoiceLoader([namespace_loader, theme_loader]),
            enable_async=True,
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    async def initialize(self) -> None:
        """初始化渲染环境。

        构建 Jinja 环境、应用自定义过滤器/全局函数、创建截图引擎，
        并加载 default 主题。可在启动钩子或首次渲染时触发，
        重复调用是安全的。
        """
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            self._jinja_env = self._build_jinja_env()
            self._jinja_env.filters.update(self._custom_filters)
            self._jinja_env.globals.update(self._custom_globals)
            self._screenshot_engine = get_screenshot_engine()
            self._theme_manager = ThemeManager(self._jinja_env)
            await self._theme_manager.load_theme("default")
            self._initialized = True

    def _require_theme_manager(self) -> ThemeManager:
        """获取已初始化的主题管理器。"""
        if not self._initialized or not self._theme_manager:
            raise RuntimeError("渲染服务尚未初始化。")
        return self._theme_manager

    # ---------- 渲染入口 ----------

    async def render(
        self, component: Renderable, use_cache: bool = False, **render_options: Any
    ) -> bytes:
        """渲染组件并直接返回图片字节。"""
        result = await self.render_full_result(
            component, use_cache=use_cache, **render_options
        )
        if result.image_bytes is None:
            raise RuntimeError("渲染成功但未能生成图片字节数据。")
        return result.image_bytes

    async def render_full_result(
        self, component: Renderable, use_cache: bool = False, **render_options: Any
    ) -> RenderResult:
        """渲染组件并返回包含图片与 HTML 的完整结果。"""
        if not self._initialized:
            await self.initialize()
        assert self._screenshot_engine is not None
        context = RenderContext(
            renderer=self,
            theme_manager=self._require_theme_manager(),
            screenshot_engine=self._screenshot_engine,
            component=component,
            use_cache=use_cache,
            render_options=render_options,
        )
        result = await self._render_with_cache(context)
        self._log_debug_html(component, result)
        return result

    async def render_to_html(
        self, component: Renderable, frameless: bool = False
    ) -> str:
        """调试入口：只执行到 HTML 生成，不进行截图。"""
        if not self._initialized:
            await self.initialize()
        context = RenderContext(
            renderer=self,
            theme_manager=self._require_theme_manager(),
            screenshot_engine=None,
            component=component,
            use_cache=False,
            render_options={"frameless": frameless},
        )
        await DependencyCollector(context).collect(component)
        return await self._require_theme_manager().render_component_to_html(
            context, frameless=frameless
        )

    async def render_html(
        self,
        html_content: str | Path,
        base_path: Path | None = None,
        *,
        use_cache: bool = False,
        apply_theme: bool = True,
        **render_options: Any,
    ) -> bytes:
        """渲染纯 HTML 内容或文件为图片。"""
        if not self._initialized:
            await self.initialize()
        assert self._screenshot_engine is not None

        if isinstance(html_content, Path):
            file_dir, html_content = _load_html_file(html_content)
            base_path = base_path or file_dir
        base_path = base_path or Path.cwd()
        if apply_theme:
            html_content = await self._wrap_html_with_theme(html_content)

        if use_cache and Config.get_config(CONFIG_MODULE, "CACHE"):
            cache_key = "html_" + hashlib.sha256(
                html_content.encode()
            ).hexdigest()
            if (cached := await self._render_cache.get(cache_key)) is not None:
                return cached
            image = await self._screenshot_engine.render(
                html=html_content, base_url_path=base_path, **render_options
            )
            await self._render_cache.set(cache_key, image)
            return image

        return await self._screenshot_engine.render(
            html=html_content, base_url_path=base_path, **render_options
        )

    async def reload_theme(self) -> str:
        """重载默认主题并清空全部缓存。

        清空清单、主题 CSS、商店与渲染缓存后重新加载 default 主题。

        返回:
            str: 重载后的主题名（固定为 "default"）。
        """
        theme_manager = self._require_theme_manager()
        theme_manager.clear_cache()
        await self._render_cache.clear()
        logger.debug("已清除UI清单缓存和渲染缓存。")
        await theme_manager.load_theme("default")
        logger.info("主题 'default' 已成功重载。")
        return "default"

    # ---------- 主题目录查询（委托 ThemeManager） ----------

    def list_available_themes(self) -> list[str]:
        """获取所有可用全局主题。

        返回:
            list[str]: 主题名称列表。
        """
        return self._require_theme_manager().list_available_themes()

    def list_page_themes(self, page_path: str) -> list[str]:
        """获取指定页面的可用页面级主题。

        参数:
            page_path: 页面路径，如 "pages/builtin/signIn"。

        返回:
            list[str]: 主题目录名列表。
        """
        return self._require_theme_manager().list_page_themes(page_path)

    def get_theme_price(self, page_path: str, theme_name: str) -> int:
        """获取页面主题价格。

        参数:
            page_path: 页面路径。
            theme_name: 主题目录名。

        返回:
            int: 主题价格，未初始化或未配置时返回 0。
        """
        if not self._initialized or not self._theme_manager:
            return 0
        return self._theme_manager.get_theme_price(page_path, theme_name)

    def get_theme_label(self, page_path: str, theme_name: str) -> str:
        """获取页面主题中文标签。

        参数:
            page_path: 页面路径。
            theme_name: 主题目录名。

        返回:
            str: 中文标签，未初始化时返回主题目录名。
        """
        if not self._initialized or not self._theme_manager:
            return theme_name
        return self._theme_manager.get_theme_label(page_path, theme_name)

    def resolve_theme_name(
        self, page_path: str, label_or_name: str
    ) -> str | None:
        """把中文标签或英文名解析为主题目录名。

        参数:
            page_path: 页面路径。
            label_or_name: 中文标签或英文目录名。

        返回:
            str | None: 匹配的主题目录名，未初始化或未匹配时返回 None。
        """
        if not self._initialized or not self._theme_manager:
            return None
        return self._theme_manager.resolve_theme_name(page_path, label_or_name)

    def resolve_feature_key(self, label_or_key: str) -> str | None:
        """把中文功能标签或英文功能键解析为功能键。

        参数:
            label_or_key: 中文标签（如"签到"）或英文键（如"sign"）。

        返回:
            str | None: 匹配的功能键，未初始化或未匹配时返回 None。
        """
        if not self._initialized or not self._theme_manager:
            return None
        return self._theme_manager.resolve_feature_key(label_or_key)

    def get_store_items(self) -> list[ThemeStoreItem]:
        """获取主题商店全部条目。

        返回:
            list[ThemeStoreItem]: 按功能分组的商店条目列表。
        """
        return self._require_theme_manager().get_store_items()

    def discover_features(self) -> dict[str, dict[str, str]]:
        """自动发现全部页面功能。

        返回:
            dict[str, dict[str, str]]: 功能键到 {page_path, label} 的映射。
        """
        return self._require_theme_manager().discover_features()

    async def resolve_user_variant(
        self, page_path: str, user_id: str
    ) -> str | None:
        """解析用户对指定页面的主题偏好。

        参数:
            page_path: 页面路径。
            user_id: 用户 ID。

        返回:
            str | None: 用户选择的主题名；默认主题或未初始化时返回 None。
        """
        if not self._initialized or not self._theme_manager:
            return None
        return await self._theme_manager.resolve_user_variant(
            page_path, user_id
        )

    # ---------- 渲染编排 ----------

    async def _render_with_cache(self, context: RenderContext) -> RenderResult:
        """带两级缓存的渲染编排。"""
        if context.use_cache and self._render_cache.enabled:
            cache_key = await self._build_cache_key(context)
        else:
            cache_key = None
        if cache_key and (cached := await self._render_cache.get(cache_key)):
            return RenderResult(
                image_bytes=cached, html_content="<!-- from cache -->"
            )

        result = await self._render_core(context)

        if cache_key and result.image_bytes:
            await self._render_cache.set(cache_key, result.image_bytes)
        return result

    async def _build_cache_key(self, context: RenderContext) -> str | None:
        """根据模板、主题、变体与渲染数据生成缓存键。"""
        try:
            resolved_data = {
                key: await value if is_coroutine_callable(value) else value
                for key, value in context.component.get_render_data().items()
            }
        except Exception as e:
            logger.warning(f"生成渲染缓存键失败: {e}", e=e)
            return None
        theme_name = (
            context.theme_manager.current_theme.name
            if context.theme_manager.current_theme
            else "default"
        )
        return render_cache_key({
            "tpl": str(context.component.template_name),
            "theme": theme_name,
            "variant": getattr(context.component, "variant", None) or "default",
            "data": resolved_data,
        })

    async def _render_core(self, context: RenderContext) -> RenderResult:
        """核心渲染流程：独立模板或主题组件。

        参数:
            context: 渲染上下文。

        返回:
            RenderResult: 渲染结果。

        异常:
            RuntimeError: 渲染过程发生异常时包装为 RuntimeError 抛出。
        """
        component = context.component
        try:
            if self._is_standalone_template(component):
                return await self._render_standalone(context)
            return await self._render_theme_component(context)
        except Exception as e:
            logger.error(
                f"渲染组件 '{component.__class__.__name__}' 时发生错误",
                "RendererService",
                e=e,
            )
            raise RuntimeError(
                f"渲染组件 '{component.__class__.__name__}' 失败"
            ) from e

    @staticmethod
    def _is_standalone_template(component: Renderable) -> bool:
        """判断组件是否为独立文件模板。

        参数:
            component: 待判断的组件。

        返回:
            bool: 组件携带绝对路径的 template_path 时返回 True。
        """
        template_path = getattr(component, "template_path", None)
        return isinstance(template_path, Path) and template_path.is_absolute()

    async def _render_standalone(self, context: RenderContext) -> RenderResult:
        """渲染独立模板文件（绝对路径，自带样式环境）。

        独立模板使用基于模板目录的临时 Jinja 环境，继承主题环境
        的全局变量与过滤器，并重写相对资源引用后截图。

        参数:
            context: 渲染上下文。

        返回:
            RenderResult: 渲染结果。
        """
        component = context.component
        template_path = Path(component.template_path)  # type: ignore[arg-type]
        template_dir = template_path.parent
        theme_env = context.theme_manager.jinja_env

        await component.prepare()
        logger.debug(f"正在渲染独立模板: '{template_path}'", "RendererService")

        env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            enable_async=True,
            autoescape=select_autoescape(["html", "xml"]),
        )
        env.globals.update(theme_env.globals)
        env.filters.update(theme_env.filters)
        env.globals["asset"] = (
            context.theme_manager.make_standalone_asset_loader(template_dir)
        )
        env.filters["md"] = markdown_filter

        data_dict = component.get_render_data()
        template = env.get_template(template_path.name)
        template_context: dict[str, Any] = {
            "theme": theme_env.globals.get("theme", {}),
            "data": data_dict,
        }
        for key, value in data_dict.items():
            if key in RESERVED_TEMPLATE_KEYS:
                logger.warning(
                    f"模板数据键 '{key}' 与渲染器保留键冲突，"
                    f"请通过 data.{key} 访问（模板: {template_path.name}）"
                )
            else:
                template_context[key] = value

        html_content = await template.render_async(**template_context)
        html_content = rewrite_urls(html_content, template_dir)

        options = self._merge_render_options(
            {}, data_dict.get("render_options"), context.render_options
        )
        return RenderResult(
            image_bytes=await self._screenshot(
                context, html_content, template_dir, options
            ),
            html_content=html_content,
        )

    async def _render_theme_component(
        self, context: RenderContext
    ) -> RenderResult:
        """渲染主题化组件：依赖收集、选项合并与页面组装。

        参数:
            context: 渲染上下文。

        返回:
            RenderResult: 渲染结果。
        """
        component = context.component
        theme_manager = context.theme_manager

        await component.prepare()
        await DependencyCollector(context).collect(component)

        data_dict = component.get_render_data()
        variant = getattr(component, "variant", None)
        template_name = await theme_manager.resolve_component_template(
            component, context
        )

        manifest_options = await theme_manager.get_render_options(
            str(component.template_name), variant, Path(template_name).name
        )
        merged_options = self._merge_render_options(
            manifest_options,
            data_dict.get("render_options"),
            context.render_options,
        )
        html_content = await theme_manager.render_component_to_html(
            context, **merged_options
        )
        if template_file := self._locate_source(template_name):
            html_content = rewrite_urls(html_content, template_file.parent)

        return RenderResult(
            image_bytes=await self._screenshot(
                context, html_content, THEMES_PATH.parent, merged_options
            ),
            html_content=html_content,
        )

    def _merge_render_options(
        self,
        template_opts: dict[str, Any],
        component_opts: Any,
        context_opts: dict[str, Any],
    ) -> dict[str, Any]:
        """按 清单 -> 组件数据 -> 调用参数 的优先级合并渲染选项。

        参数:
            template_opts: 来自清单的渲染选项。
            component_opts: 组件渲染数据中的 render_options 字段。
            context_opts: 调用方传入的渲染选项。

        返回:
            dict[str, Any]: 深度合并后的渲染选项。
        """
        merged = dict(template_opts)
        if isinstance(component_opts, dict):
            merged = deep_merge_dict(merged, component_opts)
        return deep_merge_dict(merged, context_opts)

    def _locate_source(self, template_name: str) -> Path | None:
        """定位模板的物理路径。

        参数:
            template_name: 模板名称。

        返回:
            Path | None: 模板的物理路径，定位失败时返回 None。
        """
        theme_env = self._require_theme_manager().jinja_env
        if not theme_env.loader:
            return None
        try:
            _source, filepath, _uptodate = theme_env.loader.get_source(
                theme_env, template_name
            )
        except Exception:
            return None
        return Path(filepath) if filepath else None

    async def _screenshot(
        self,
        context: RenderContext,
        html_content: str,
        base_url_path: Path,
        options: dict[str, Any],
    ) -> bytes:
        """调用截图引擎，剥离仅作用于 HTML 组装阶段的选项。

        参数:
            context: 渲染上下文。
            html_content: 已组装完成的 HTML 内容。
            base_url_path: 解析相对资源的基础目录。
            options: 合并后的渲染选项。

        返回:
            bytes: 渲染后的 PNG 图片字节数据。
        """
        assert context.screenshot_engine is not None
        screenshot_options = {
            key: value
            for key, value in options.items()
            if key not in _HTML_ONLY_OPTIONS
        }
        return await context.screenshot_engine.render(
            html=html_content,
            base_url_path=base_url_path,
            **screenshot_options,
        )

    # ---------- 辅助 ----------

    def _log_debug_html(
        self, component: Renderable, result: RenderResult
    ) -> None:
        """调试模式下输出渲染的 HTML 片段。

        参数:
            component: 已渲染的组件。
            result: 渲染结果。
        """
        if Config.get_config(CONFIG_MODULE, DEBUG_CONFIG_KEY) and (
            result.html_content
        ):
            logger.info(
                f"--- [UI DEBUG] HTML for "
                f"{component.__class__.__name__} ---\n"
                f"{result.html_content[:500]}...\n"
                f"--- [UI DEBUG] End of HTML ---"
            )

    async def _wrap_html_with_theme(self, html_content: str) -> str:
        """把裸 HTML 包裹进主题框架（仅注入主题 CSS）。

        参数:
            html_content: 裸 HTML 内容。

        返回:
            str: 包含文档骨架与主题 CSS 的完整 HTML。
        """
        theme_manager = self._require_theme_manager()
        if not theme_manager.current_theme:
            return html_content
        try:
            template = theme_manager.jinja_env.get_template("theme.css.jinja")
            theme_css = await template.render_async(
                theme=model_dump(theme_manager.current_theme)
            )
        except Exception as e:
            logger.warning(f"生成主题 CSS 失败: {e}")
            theme_css = ""
        return (
            '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n'
            '    <meta charset="UTF-8">\n'
            '    <meta name="viewport" content='
            '"width=device-width, initial-scale=1.0">\n'
            f"    <style>{theme_css}</style>\n"
            f"</head>\n<body>\n{html_content}\n</body>\n</html>"
        )
