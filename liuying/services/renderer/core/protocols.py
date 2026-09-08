"""渲染协议与结果模型。

定义渲染体系的最小契约：
- Renderable: 任何可被渲染服务处理的 UI 组件必须实现的抽象基类
- ScreenshotEngine: 截图后端协议，允许在不同引擎间替换
- RenderResult: 渲染过程的统一返回类型
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Iterable
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel


class Renderable(ABC):
    """可渲染组件的抽象基类。

    渲染服务通过该协议以统一方式处理所有 UI 组件：
    使用 template_name 定位模板，get_render_data 提供模板上下文，
    get_children 支撑组件树的依赖收集。
    """

    component_css: str | None

    @property
    @abstractmethod
    def template_name(self) -> str:
        """返回组件对应的模板路径。

        返回:
            str: 模板路径，例如 'components/core/card'。
        """
        ...

    async def prepare(self) -> None:
        """渲染前的异步预处理钩子。

        在组件数据被传递给模板之前调用，适合执行数据库查询、
        网络请求等耗时操作以准备最终的渲染数据。
        """

    @abstractmethod
    def get_children(self) -> Iterable["Renderable"]:
        """返回直接子组件的可迭代对象。

        渲染服务据此递归遍历组件树以收集 CSS/JS 依赖，
        叶子组件应返回空元组。

        返回:
            Iterable[Renderable]: 直接子组件集合。
        """
        ...

    def get_required_scripts(self) -> list[str]:
        """返回组件所需的 JS 脚本路径列表。

        返回:
            list[str]: 相对于主题 assets 目录的脚本路径。
        """
        return []

    def get_required_styles(self) -> list[str]:
        """返回组件所需的 CSS 样式路径列表。

        返回:
            list[str]: 相对于主题 assets 目录的样式路径。
        """
        return []

    @abstractmethod
    def get_render_data(self) -> dict[str, Any | Awaitable[Any]]:
        """返回传递给模板的上下文数据字典。

        字典的值可以是协程，渲染服务会在模板渲染前自动解析它们。

        返回:
            dict[str, Any | Awaitable[Any]]: 模板渲染上下文数据。
        """
        ...

    def get_extra_css(self, context: Any) -> str | Awaitable[str]:
        """组件提供的额外 CSS 生命周期钩子。

        参数:
            context: 当前渲染上下文对象，可访问主题管理器等。

        返回:
            str | Awaitable[str]: 注入到页面的额外 CSS 字符串或协程。
        """
        return ""


class ScreenshotEngine(Protocol):
    """截图引擎协议，将 HTML 字符串截图为图片。"""

    async def render(
        self, html: str, base_url_path: Path, **render_options: Any
    ) -> bytes:
        """将 HTML 内容渲染为图片字节。

        参数:
            html: 要渲染的 HTML 内容。
            base_url_path: 用于解析相对路径资源的基础目录。
            **render_options: 传递给底层截图库的额外选项。

        返回:
            bytes: 渲染后的 PNG 图片字节数据。
        """
        ...


class RenderResult(BaseModel):
    """渲染服务的统一返回类型。"""

    image_bytes: bytes | None = None
    """渲染生成的图片字节，失败时为 None"""
    html_content: str | None = None
    """渲染过程的 HTML 内容，用于调试"""
