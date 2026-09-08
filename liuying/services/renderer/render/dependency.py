"""组件树依赖收集器：递归收集样式、脚本与内联 CSS。"""

import asyncio
import inspect
from pathlib import Path, PurePosixPath

from jinja2 import TemplateNotFound

from liuying.services.log import logger
from liuying.services.renderer.core.config import RESOLVE_TIMEOUT
from liuying.services.renderer.core.context import RenderContext
from liuying.services.renderer.core.protocols import Renderable
from liuying.services.renderer.core.utils import rewrite_urls


class DependencyCollector:
    """按组件树递归收集渲染所需的全部依赖，结果写入 RenderContext。"""

    def __init__(self, context: RenderContext) -> None:
        """初始化收集器。

        参数:
            context: 渲染上下文，收集结果直接写入其中的集合字段。
        """
        self._context = context
        self._theme_manager = context.theme_manager

    async def collect(self, component: Renderable) -> None:
        """从根组件开始递归收集依赖。

        参数:
            component: 根组件。
        """
        await self._walk(component)

    async def _walk(self, component: Renderable) -> None:
        """深度优先遍历组件树，逐组件收集依赖。

        参数:
            component: 当前处理的组件节点。
        """
        if id(component) in self._context.processed_components:
            return
        self._context.processed_components.add(id(component))

        component_path = str(component.template_name)
        variant = getattr(component, "variant", None)
        manifest = await self._safe_manifest(component_path, variant)

        for style_path in self._resolve_style_paths(
            manifest, component_path, variant
        ):
            await self._load_component_style(style_path)

        self._context.collected_scripts.update(component.get_required_scripts())
        self._context.collected_asset_styles.update(
            component.get_required_styles()
        )

        if (css_result := component.get_extra_css(self._context)) is not None:
            css = (
                await css_result if inspect.isawaitable(css_result) else css_result
            )
            if css:
                self._context.collected_inline_css.append(str(css))

        for child in component.get_children():
            if child:
                await self._walk(child)

    async def _safe_manifest(
        self, component_path: str, variant: str | None
    ) -> dict | None:
        """获取组件 manifest.json，超时时降级为 None。

        参数:
            component_path: 组件模板路径。
            variant: 组件的变体名称。

        返回:
            dict | None: 组件清单，超时或缺失时返回 None。
        """
        try:
            return await asyncio.wait_for(
                self._theme_manager.get_component_manifest(component_path),
                timeout=RESOLVE_TIMEOUT,
            )
        except TimeoutError:
            logger.warning(f"收集组件 '{component_path}' 依赖超时，跳过清单")
            return None

    def _resolve_style_paths(
        self, manifest: dict | None, component_path: str, variant: str | None
    ) -> list[str]:
        """解析组件需要加载的样式模板路径列表。

        参数:
            manifest: 组件清单，其中的 styles 字段为样式文件或列表。
            component_path: 组件模板路径。
            variant: 组件的变体名称。

        返回:
            list[str]: 样式模板路径列表，清单未声明时默认尝试 style.css。
        """
        if manifest and "styles" in manifest:
            declared = manifest["styles"]
            declared_list = (
                [declared] if isinstance(declared, str) else list(declared)
            )
            return [
                self._with_fallback(component_path, style, variant)
                for style in declared_list
            ]
        return [self._with_fallback(component_path, "style.css", variant)]

    def _with_fallback(
        self, component_path: str, style_file: str, variant: str | None
    ) -> str:
        """按 变体 -> default -> 组件根 的顺序解析样式路径。

        参数:
            component_path: 组件模板路径。
            style_file: 样式文件名。
            variant: 组件的变体名称。

        返回:
            str: 第一个存在的样式路径；全部缺失时返回最后一个候选。
        """
        base = PurePosixPath(component_path)
        candidates: list[str] = []
        if variant and variant != "default":
            candidates.append(str(base / variant / style_file))
            candidates.append(str(base / "skins" / variant / style_file))
        candidates.append(str(base / "default" / style_file))
        candidates.append(str(base / style_file))

        env = self._theme_manager.jinja_env
        for candidate in candidates:
            try:
                env.get_template(candidate)
                return candidate
            except TemplateNotFound:
                continue
        return candidates[-1]

    async def _load_component_style(self, style_path: str) -> None:
        """渲染样式模板并注入上下文的内联 CSS 列表。

        参数:
            style_path: 样式模板路径。
        """
        env = self._theme_manager.jinja_env
        try:
            template = env.get_template(style_path)
        except TemplateNotFound:
            return
        theme_globals = env.globals.get("theme", {})
        content = await template.render_async(theme=theme_globals)
        if template.filename:
            content = rewrite_urls(
                content, Path(template.filename).parent, is_css=True
            )
        self._context.collected_inline_css.append(content)
