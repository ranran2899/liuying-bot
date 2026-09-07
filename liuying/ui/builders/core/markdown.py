"""链式构建 Markdown 图片的辅助类，支持上下文管理与组合。"""

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from ...models.core.base import RenderableComponent
from ...models.core.markdown import (
    CodeElement,
    ComponentElement,
    HeadingElement,
    ImageElement,
    ListElement,
    ListItemElement,
    MarkdownData,
    MarkdownElement,
    QuoteElement,
    RawHtmlElement,
    TableElement,
    TextElement,
)
from ..base import BaseBuilder, resolve_image_src, to_component

__all__ = ["MarkdownBuilder"]


class MarkdownBuilder(BaseBuilder[MarkdownData]):
    """链式构建 Markdown 图片的辅助类，支持上下文管理与组合。"""

    def __init__(self):
        """初始化空的 Markdown 构建器，默认宽度 800px。"""
        data_model = MarkdownData(elements=[], width=800, css_path=None)
        super().__init__(data_model, template_name="components/core/markdown")
        self._parts: list[MarkdownElement] = []
        self._width: int = 800
        self._css_path: str | None = None
        self._context_stack: list[QuoteElement | ListElement | ListItemElement] = []

    def _append_element(self, element: MarkdownElement) -> "MarkdownBuilder":
        """根据上下文把元素添加到正确位置。

        存在未退出的引用/列表上下文时追加到容器内，否则追加到顶层。

        参数:
            element: 待追加的 Markdown 元素。

        返回:
            MarkdownBuilder: 构建器自身，支持链式调用。
        """
        target = (
            self._context_stack[-1].content if self._context_stack else self._parts
        )
        target.append(element)
        return self

    def text(self, text: str) -> "MarkdownBuilder":
        """添加 Markdown 文本。

        参数:
            text: 文本内容。

        返回:
            MarkdownBuilder: 构建器自身，支持链式调用。
        """
        return self._append_element(TextElement(text=text))

    def head(self, text: str, level: int = 1) -> "MarkdownBuilder":
        """添加 Markdown 标题。

        参数:
            text: 标题文本。
            level: 标题级别，1-6。

        返回:
            MarkdownBuilder: 构建器自身，支持链式调用。
        """
        return self._append_element(HeadingElement(text=text, level=level))

    def image(self, content: str | Path, alt: str = "image") -> "MarkdownBuilder":
        """添加 Markdown 图片。

        参数:
            content: 图片来源，支持文件路径与 `base64://` 前缀的数据。
            alt: 图片的替代文本。

        返回:
            MarkdownBuilder: 构建器自身，支持链式调用。
        """
        return self._append_element(
            ImageElement(src=resolve_image_src(content), alt=alt)
        )

    def code(self, code: str, language: str = "") -> "MarkdownBuilder":
        """添加 Markdown 代码块。

        参数:
            code: 代码内容。
            language: 代码语言，用于语法高亮标注。

        返回:
            MarkdownBuilder: 构建器自身，支持链式调用。
        """
        return self._append_element(CodeElement(code=code, language=language))

    def table(
        self,
        headers: list[str],
        rows: list[list[str]],
        alignments: list[Any] | None = None,
    ) -> "MarkdownBuilder":
        """添加 Markdown 表格。

        参数:
            headers: 表头列表。
            rows: 数据行列表。
            alignments: 每列的对齐方式列表（left/center/right）。

        返回:
            MarkdownBuilder: 构建器自身，支持链式调用。
        """
        return self._append_element(
            TableElement(headers=headers, rows=rows, alignments=alignments)
        )

    def add_component(
        self, component: "BaseBuilder | RenderableComponent"
    ) -> "MarkdownBuilder":
        """添加一个 UI 组件（如图表、卡片等）。

        参数:
            component: 组件模型或构建器。

        返回:
            MarkdownBuilder: 构建器自身，支持链式调用。
        """
        return self._append_element(
            ComponentElement(component=to_component(component))
        )

    def add_builder(self, builder: "MarkdownBuilder") -> "MarkdownBuilder":
        """把另一个 MarkdownBuilder 的内容组合进来。

        参数:
            builder: 另一个 Markdown 构建器。

        返回:
            MarkdownBuilder: 构建器自身，支持链式调用。
        """
        target = (
            self._context_stack[-1].content if self._context_stack else self._parts
        )
        target.extend(builder._parts)
        return self

    def quote(self) -> AbstractContextManager["MarkdownBuilder"]:
        """创建一个引用块上下文。

        返回:
            AbstractContextManager[MarkdownBuilder]: 上下文管理器，
                with 块内的元素会进入引用块。

        示例:
            with md.quote():
                md.text("引用内容")
        """
        return self._context_for(QuoteElement())

    def add_list(
        self, ordered: bool = False
    ) -> AbstractContextManager["MarkdownBuilder"]:
        """创建一个列表上下文。

        参数:
            ordered: 是否为有序列表。

        返回:
            AbstractContextManager[MarkdownBuilder]: 上下文管理器，
                with 块内通过 list_item() 添加列表项。
        """
        return self._context_for(ListElement(ordered=ordered))

    def list_item(self) -> AbstractContextManager["MarkdownBuilder"]:
        """在列表上下文中创建一个列表项。

        返回:
            AbstractContextManager[MarkdownBuilder]: 上下文管理器。

        异常:
            TypeError: 当前不在 add_list() 上下文中时抛出。
        """
        if not self._context_stack or not isinstance(
            self._context_stack[-1], ListElement
        ):
            raise TypeError("list_item() 只能在 add_list() 上下文中使用。")
        return self._context_for(ListItemElement())

    class _ContextManager:
        """把元素压入/弹出构建器上下文栈的上下文管理器。"""

        def __init__(
            self,
            builder: "MarkdownBuilder",
            element: QuoteElement | ListElement | ListItemElement,
        ):
            """初始化上下文管理器。

            参数:
                builder: 所属的 Markdown 构建器。
                element: 上下文对应的容器元素。
            """
            self.builder = builder
            self.element = element

        def __enter__(self) -> "MarkdownBuilder":
            """进入上下文，把容器元素压入构建器栈。

            返回:
                MarkdownBuilder: 构建器自身。
            """
            self.builder._context_stack.append(self.element)
            return self.builder

        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            """退出上下文，把容器元素弹出构建器栈。"""
            self.builder._context_stack.pop()

    def _context_for(
        self, element: QuoteElement | ListElement | ListItemElement
    ) -> AbstractContextManager["MarkdownBuilder"]:
        """为容器元素创建上下文管理器。

        参数:
            element: 容器元素（引用/列表/列表项）。

        返回:
            AbstractContextManager[MarkdownBuilder]: 上下文管理器。
        """
        self._append_element(element)
        return self._ContextManager(self, element)

    def set_width(self, width: int) -> "MarkdownBuilder":
        """设置图片宽度。

        参数:
            width: 图片宽度（像素）。

        返回:
            MarkdownBuilder: 构建器自身，支持链式调用。
        """
        self._width = width
        return self

    def set_css_path(self, css_path: str) -> "MarkdownBuilder":
        """设置 CSS 样式路径。

        参数:
            css_path: 自定义 CSS 文件的绝对路径。

        返回:
            MarkdownBuilder: 构建器自身，支持链式调用。
        """
        self._css_path = css_path
        return self

    def add_divider(self) -> "MarkdownBuilder":
        """添加一条标准的 Markdown 分割线。

        返回:
            MarkdownBuilder: 构建器自身，支持链式调用。
        """
        return self._append_element(RawHtmlElement(html="---"))

    def build(self) -> MarkdownData:
        """构建并返回 MarkdownData 模型实例。

        把累积的元素、宽度与 CSS 路径写入数据模型。

        返回:
            MarkdownData: 配置完成的数据模型实例。
        """
        self._data.elements = self._parts
        self._data.width = self._width
        self._data.css_path = self._css_path
        return super().build()
