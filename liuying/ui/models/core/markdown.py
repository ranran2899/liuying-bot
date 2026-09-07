"""Markdown 文档数据模型，支持元素级构建与组件嵌入。"""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

import aiofiles
from pydantic import BaseModel, Field

from liuying.services.log import logger

from .base import ContainerComponent, RenderableComponent

__all__ = [
    "CodeElement",
    "ComponentElement",
    "ContainerElement",
    "HeadingElement",
    "ImageElement",
    "ListElement",
    "ListItemElement",
    "MarkdownData",
    "MarkdownElement",
    "QuoteElement",
    "RawHtmlElement",
    "TableElement",
    "TextElement",
]


def _readable_css(path: Path) -> Path | None:
    """同步检查 CSS 文件是否可读。

    避免在协程内使用 pathlib 阻塞方法。

    参数:
        path: CSS 文件路径。

    返回:
        Path | None: 文件存在时返回原路径，否则返回 None。
    """
    return path if path.is_file() else None


async def _read_css(path: Path) -> str:
    """异步读取 CSS 文件内容。

    参数:
        path: CSS 文件路径。

    返回:
        str: 文件文本内容。
    """
    async with aiofiles.open(path, encoding="utf-8") as f:
        return await f.read()


class MarkdownElement(BaseModel, ABC):
    """Markdown 元素基类。"""

    @abstractmethod
    def to_markdown(self) -> str:
        """将元素序列化为 Markdown 字符串。

        返回:
            str: 该元素的 Markdown 表示。
        """
        raise NotImplementedError


class TextElement(MarkdownElement):
    """文本元素。"""

    type: Literal["text"] = "text"
    text: str

    def to_markdown(self) -> str:
        return self.text


class HeadingElement(MarkdownElement):
    """标题元素。"""

    type: Literal["heading"] = "heading"
    text: str
    level: int = Field(..., ge=1, le=6, description="标题级别 (1-6)")

    def to_markdown(self) -> str:
        return f"{'#' * self.level} {self.text}"


class ImageElement(MarkdownElement):
    """图片元素。"""

    type: Literal["image"] = "image"
    src: str
    alt: str = "image"

    def to_markdown(self) -> str:
        return f"![{self.alt}]({self.src})"


class CodeElement(MarkdownElement):
    """代码块元素。"""

    type: Literal["code"] = "code"
    code: str
    language: str = ""

    def to_markdown(self) -> str:
        return f"```{self.language}\n{self.code}\n```"


class RawHtmlElement(MarkdownElement):
    """原始 HTML 元素。"""

    type: Literal["raw_html"] = "raw_html"
    html: str

    def to_markdown(self) -> str:
        return self.html


class TableElement(MarkdownElement):
    """表格元素。"""

    type: Literal["table"] = "table"
    headers: list[str]
    rows: list[list[str]]
    alignments: list[Literal["left", "center", "right"]] | None = None

    _ALIGN_MAP: dict[str, str] = {"left": ":---", "center": ":---:", "right": "---:"}

    def to_markdown(self) -> str:
        header_row = "| " + " | ".join(self.headers) + " |"
        if self.alignments:
            separator = (
                "| "
                + " | ".join(
                    self._ALIGN_MAP.get(a, "---") for a in self.alignments
                )
                + " |"
            )
        else:
            separator = "| " + " | ".join(["---"] * len(self.headers)) + " |"
        data_rows = "\n".join(
            "| " + " | ".join(map(str, row)) + " |" for row in self.rows
        )
        return f"{header_row}\n{separator}\n{data_rows}"


class ContainerElement(MarkdownElement):
    """容器元素基类。"""

    content: list[MarkdownElement] = Field(
        default_factory=list, description="容器内包含的元素列表"
    )


class QuoteElement(ContainerElement):
    """引用块元素。"""

    type: Literal["quote"] = "quote"

    def to_markdown(self) -> str:
        inner = "\n".join(part.to_markdown() for part in self.content)
        return "\n".join(f"> {line}" for line in inner.split("\n"))


class ListItemElement(ContainerElement):
    """列表项元素。"""

    def to_markdown(self) -> str:
        return "\n".join(part.to_markdown() for part in self.content)


class ListElement(ContainerElement):
    """列表元素。"""

    type: Literal["list"] = "list"
    ordered: bool = False

    def to_markdown(self) -> str:
        lines = []
        for i, item in enumerate(self.content):
            if isinstance(item, ListItemElement):
                prefix = f"{i + 1}." if self.ordered else "*"
                lines.append(f"{prefix} {item.to_markdown()}")
        return "\n".join(lines)


class ComponentElement(MarkdownElement):
    """在 Markdown 流中嵌入另一个可渲染组件的特殊元素。"""

    type: Literal["component"] = "component"
    component: RenderableComponent

    def to_markdown(self) -> str:
        return ""


class MarkdownData(ContainerComponent):
    """Markdown 转图片的数据模型。"""

    style_name: str | None = None
    elements: list[MarkdownElement] = Field(
        default_factory=list, description="构成文档的元素列表"
    )
    """构成文档的元素列表"""
    width: int = 800
    css_path: str | None = None

    @property
    def template_name(self) -> str:
        return "components/core/markdown"

    def get_children(self) -> Iterable[RenderableComponent]:
        """递归找出嵌入的所有组件，供 CSS/JS 依赖收集。

        返回:
            Iterable[RenderableComponent]: 嵌套在各元素中的组件
                （含组件自身的子组件）。
        """

        def find_components(
            elements: list[MarkdownElement],
        ) -> Iterable[RenderableComponent]:
            for element in elements:
                match element:
                    case ComponentElement(component=comp):
                        yield comp
                        yield from comp.get_children()
                    case ContainerElement():
                        yield from find_components(element.content)

        yield from find_components(self.elements)

    async def get_extra_css(self, context: Any) -> str:
        """按自定义路径或具名样式加载 Markdown 的额外 CSS。

        优先使用 css_path 指定的自定义文件；否则按 style_name
        经主题管理器解析具名样式。

        参数:
            context: 渲染上下文，用于访问主题管理器。

        返回:
            str: CSS 文本，来源缺失或文件不存在时返回空字符串。
        """
        if self.css_path:
            css_file = _readable_css(Path(self.css_path))
            if css_file:
                return await _read_css(css_file)
            logger.warning(f"Markdown 自定义 CSS 文件不存在: {self.css_path}")
            return ""

        style_name = self.style_name or "light"
        style_path = await context.theme_manager.resolve_markdown_style_path(
            style_name, context
        )
        if css_file := (_readable_css(style_path) if style_path else None):
            return await _read_css(css_file)
        return ""
