"""链式构建轻量级富文本组件的辅助类。"""

from typing import Literal, Self

from ...models.core.text import TextData, TextSpan
from ..base import BaseBuilder

__all__ = ["TextBuilder"]


class TextBuilder(BaseBuilder[TextData]):
    """链式构建轻量级富文本组件的辅助类。"""

    def __init__(self, text: str = ""):
        """初始化富文本构建器。

        参数:
            text: 初始文本，非空时自动添加为第一个片段。
        """
        data_model = TextData(spans=[], align="left")
        super().__init__(data_model, template_name="components/core/text")
        if text:
            self.add_span(text)

    def set_alignment(self, align: Literal["left", "right", "center"]) -> Self:
        """设置整个文本块的对齐方式。

        参数:
            align: 对齐方式（left/center/right）。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.align = align
        return self

    def add_span(
        self,
        text: str,
        *,
        bold: bool = False,
        italic: bool = False,
        underline: bool = False,
        strikethrough: bool = False,
        code: bool = False,
        color: str | None = None,
        font_size: str | int | None = None,
        font_family: str | None = None,
    ) -> Self:
        """添加一个带有样式的文本片段。

        参数:
            text: 片段文本。
            bold: 是否加粗。
            italic: 是否斜体。
            underline: 是否下划线。
            strikethrough: 是否删除线。
            code: 是否渲染为行内代码样式。
            color: 文本颜色（CSS 颜色值）。
            font_size: 字号，整数按像素处理，或直接传 CSS 值。
            font_family: 字体族。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        size = f"{font_size}px" if isinstance(font_size, int) else font_size
        self._data.spans.append(TextSpan(
            text=text,
            bold=bold,
            italic=italic,
            underline=underline,
            strikethrough=strikethrough,
            code=code,
            color=color,
            font_size=size,
            font_family=font_family,
        ))
        return self
