"""UI模块顶层接口，提供便捷的工厂函数和统一的渲染入口。"""

from pathlib import Path
from typing import Any

from liuying.services.renderer.protocols import Renderable, RenderResult

from . import builders
from .builders.core.layout import LayoutBuilder
from .models.core.base import RenderableComponent
from .models.core.markdown import MarkdownData
from .models.core.template import TemplateComponent


def template(path: str | Path, data: dict[str, Any]) -> TemplateComponent:
    """创建一个基于独立模板文件的UI组件。

    参数:
        path: 指向HTML模板文件的绝对或相对路径。
        data: 传递给模板的上下文数据字典。

    返回:
        TemplateComponent: 可被 render() 处理的组件实例。
    """
    if isinstance(path, str):
        path = Path(path)
    return TemplateComponent(template_path=path, data=data)


def _apply_markdown_style(
    component: MarkdownData, style: str | Path | None
) -> MarkdownData:
    """为Markdown组件应用样式配置。"""
    match style:
        case Path():
            component.css_path = str(style.absolute())
        case str() | None:
            component.style_name = style
    return component


def markdown(content: str, style: str | Path | None = "default") -> MarkdownData:
    """创建一个基于Markdown内容的UI组件。

    参数:
        content: 要渲染的Markdown字符串。
        style: Markdown的样式名称或自定义CSS文件路径。

    返回:
        MarkdownData: 可被 render() 处理的组件实例。
    """
    component = builders.MarkdownBuilder().text(content).build()
    return _apply_markdown_style(component, style)


def vstack(children: list[RenderableComponent], **layout_options) -> LayoutBuilder:
    """创建一个垂直布局组件。

    参数:
        children: RenderableComponent 实例列表。
        **layout_options: 传递给布局模板的额外选项。

    返回:
        LayoutBuilder: 配置好的垂直布局构建器。
    """
    builder = LayoutBuilder.column(**layout_options)
    for child in children:
        builder.add_item(child)
    return builder


def hstack(children: list[RenderableComponent], **layout_options) -> LayoutBuilder:
    """创建一个水平布局组件。

    参数:
        children: RenderableComponent 实例列表。
        **layout_options: 传递给布局模板的额外选项。

    返回:
        LayoutBuilder: 配置好的水平布局构建器。
    """
    builder = LayoutBuilder.row(**layout_options)
    for child in children:
        builder.add_item(child)
    return builder


async def _resolve_variant(
    component: Renderable, variant: str | None, user_id: str | None
) -> None:
    """解析并设置组件的变体/皮肤。"""
    if variant and hasattr(component, "variant"):
        component.variant = variant
        return
    if user_id and hasattr(component, "variant"):
        template_path = getattr(component, "template_path", None)
        if template_path:
            from liuying.services.renderer import renderer_service
            resolved = await renderer_service.resolve_user_variant(
                str(template_path), user_id
            )
            if resolved:
                component.variant = resolved


async def render(
    component_or_path: Renderable | str | Path,
    data: dict | None = None,
    *,
    use_cache: bool = False,
    variant: str | None = None,
    user_id: str | None = None,
    **kwargs,
) -> bytes:
    """统一的UI渲染入口。

    参数:
        component_or_path: Renderable 实例或模板路径。
        data: 模板数据字典。
        use_cache: 是否启用文件缓存。
        variant: 显式指定变体名称，优先级高于 user_id 自动解析。
        user_id: 用户ID，用于自动解析用户主题偏好。
        **kwargs: 传递给截图引擎的额外参数。

    返回:
        bytes: 渲染后的PNG图片字节数据。
    """
    from liuying.services.renderer import renderer_service

    if isinstance(component_or_path, str | Path):
        if data is None:
            raise ValueError("使用模板路径渲染时必须提供 'data' 参数。")
        component: Renderable = TemplateComponent(
            template_path=component_or_path, data=data
        )
    else:
        component = component_or_path

    await _resolve_variant(component, variant, user_id)

    return await renderer_service.render(
        component, use_cache=use_cache, **kwargs
    )


async def render_template(
    path: str | Path,
    data: dict,
    use_cache: bool = False,
    variant: str | None = None,
    user_id: str | None = None,
    **kwargs,
) -> bytes:
    """渲染一个独立的Jinja2模板文件。

    参数:
        path: 模板文件路径，相对于主题模板目录。
        data: 传递给模板的数据字典。
        use_cache: 是否启用渲染缓存。
        variant: 显式指定变体名称。
        user_id: 用户ID，用于自动解析用户主题偏好。
        **kwargs: 传递给渲染服务的额外参数。

    返回:
        bytes: 渲染后的图片数据。
    """
    return await render(
        path, data, use_cache=use_cache,
        variant=variant, user_id=user_id, **kwargs
    )


async def render_markdown(
    md: str, style: str | Path | None = "default",
    use_cache: bool = False, **kwargs
) -> bytes:
    """将Markdown字符串渲染为图片。

    参数:
        md: 要渲染的Markdown内容字符串。
        style: 样式名称或自定义CSS文件路径。
        use_cache: 是否启用渲染缓存。
        **kwargs: 传递给渲染服务的额外参数。

    返回:
        bytes: 渲染后的图片数据。
    """
    component = builders.MarkdownBuilder().text(md).build()
    _apply_markdown_style(component, style)
    return await render(component, use_cache=use_cache, **kwargs)


async def render_full_result(
    component: Renderable, use_cache: bool = False, **kwargs
) -> RenderResult:
    """渲染组件并返回包含图片和HTML的完整结果对象。

    参数:
        component: Renderable 实例。
        use_cache: 是否启用文件缓存。
        **kwargs: 传递给截图引擎的额外参数。

    返回:
        RenderResult: 包含 image_bytes 和 html_content 的结果。
    """
    from liuying.services.renderer import renderer_service
    return await renderer_service.render_full_result(
        component, use_cache=use_cache, **kwargs
    )


__all__ = [
    "builders",
    "hstack",
    "markdown",
    "render",
    "render_full_result",
    "render_markdown",
    "render_template",
    "template",
    "vstack",
]
