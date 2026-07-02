"""
Markdown组件模块
"""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

import aiofiles
from pydantic import BaseModel, Field

from liuying.services.log import logger

from .base import ContainerComponent, RenderableComponent


class MarkdownElement(BaseModel, ABC):
    """Markdown元素基类"""

    @abstractmethod
    def to_markdown(self) -> str:
        """将元素序列化为Markdown字符串表示。"""
        pass


class TextElement(MarkdownElement):
    """文本元素"""

    type: Literal["text"] = "text"
    text: str

    def to_markdown(self) -> str:
        return self.text


class HeadingElement(MarkdownElement):
    """标题元素"""

    type: Literal["heading"] = "heading"
    text: str
    level: int = Field(..., ge=1, le=6, description="标题级别 (1-6)")

    def to_markdown(self) -> str:
        return f"{'#' * self.level} {self.text}"


class ImageElement(MarkdownElement):
    """图片元素"""

    type: Literal["image"] = "image"
    src: str
    alt: str = "image"

    def to_markdown(self) -> str:
        return f"![{self.alt}]({self.src})"


class CodeElement(MarkdownElement):
    """代码块元素"""

    type: Literal["code"] = "code"
    code: str
    language: str = ""

    def to_markdown(self) -> str:
        return f"```{self.language}\n{self.code}\n```"


class RawHtmlElement(MarkdownElement):
    """原始HTML元素"""

    type: Literal["raw_html"] = "raw_html"
    html: str

    def to_markdown(self) -> str:
        return self.html


class TableElement(MarkdownElement):
    """表格元素"""

    type: Literal["table"] = "table"
    headers: list[str]
    rows: list[list[str]]
    alignments: list[Literal["left", "center", "right"]] | None = None

    _ALIGN_MAP: dict[str, str] = {"left": ":---", "center": ":---:", "right": "---:"}

    def to_markdown(self) -> str:
        header_row = "| " + " | ".join(self.headers) + " |"
        if self.alignments:
            separator_row = (
                "| "
                + " | ".join(
                    self._ALIGN_MAP.get(a, "---") for a in self.alignments
                )
                + " |"
            )
        else:
            separator_row = "| " + " | ".join(["---"] * len(self.headers)) + " |"
        data_rows = "\n".join(
            "| " + " | ".join(map(str, row)) + " |" for row in self.rows
        )
        return f"{header_row}\n{separator_row}\n{data_rows}"


class ContainerElement(MarkdownElement):
    """容器元素基类"""

    content: list[MarkdownElement] = Field(
        default_factory=list, description="容器内包含的Markdown元素列表"
    )


class QuoteElement(ContainerElement):
    """引用块元素"""

    type: Literal["quote"] = "quote"

    def to_markdown(self) -> str:
        inner_md = "\n".join(part.to_markdown() for part in self.content)
        return "\n".join([f"> {line}" for line in inner_md.split("\n")])


class ListItemElement(ContainerElement):
    """列表项元素"""

    def to_markdown(self) -> str:
        return "\n".join(part.to_markdown() for part in self.content)


class ListElement(ContainerElement):
    """列表元素"""

    type: Literal["list"] = "list"
    ordered: bool = False

    def to_markdown(self) -> str:
        lines = []
        for i, item in enumerate(self.content):
            if isinstance(item, ListItemElement):
                prefix = f"{i + 1}." if self.ordered else "*"
                item_content = item.to_markdown()
                lines.append(f"{prefix} {item_content}")
        return "\n".join(lines)


class ComponentElement(MarkdownElement):
    """一个特殊的元素，用于在Markdown流中持有另一个可渲染组件。"""

    type: Literal["component"] = "component"
    component: RenderableComponent

    def to_markdown(self) -> str:
        return ""


class MarkdownData(ContainerComponent):
    """Markdown转图片的数据模型"""

    style_name: str | None = None
    elements: list[MarkdownElement] = Field(
        default_factory=list, description="构成Markdown文档的元素列表"
    )
    width: int = 800
    css_path: str | None = None

    @property
    def template_name(self) -> str:
        return "components/core/markdown"

    def get_children(self) -> Iterable[RenderableComponent]:
        """让CSS/JS依赖收集器能够递归地找到所有嵌入的组件。"""

        def find_components_recursive(
            elements: list[MarkdownElement],
        ) -> Iterable[RenderableComponent]:
            for element in elements:
                if isinstance(element, ComponentElement):
                    yield element.component
                    if hasattr(element.component, "get_children"):
                        yield from element.component.get_children()
                elif isinstance(element, ContainerElement):
                    yield from find_components_recursive(element.content)

        yield from find_components_recursive(self.elements)

    async def get_extra_css(self, context: Any) -> str:
        if self.css_path:
            css_file = Path(self.css_path)
            if css_file.is_file():
                async with aiofiles.open(css_file, encoding="utf-8") as f:
                    return await f.read()
            else:
                logger.warning(f"Markdown自定义CSS文件不存在: {self.css_path}")
        else:
            style_name = self.style_name or "light"
            css_path = await context.theme_manager.resolve_markdown_style_path(
                style_name, context
            )
            if css_path and css_path.exists():
                async with aiofiles.open(css_path, encoding="utf-8") as f:
                    return await f.read()
        return ""


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
