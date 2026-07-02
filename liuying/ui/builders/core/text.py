from typing import Literal, Self

from ...models.core.text import TextData, TextSpan
from ..base import BaseBuilder


class TextBuilder(BaseBuilder[TextData]):
    """链式构建轻量级富文本组件的辅助类。"""

    def __init__(self, text: str = ""):
        data_model = TextData(spans=[], align="left")
        super().__init__(data_model, template_name="components/core/text")
        if text:
            self.add_span(text)

    def set_alignment(self, align: Literal["left", "right", "center"]) -> Self:
        """设置整个文本块的对齐方式。"""
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
        """添加一个带有样式的文本片段。"""
        font_size_str = f"{font_size}px" if isinstance(font_size, int) else font_size
        self._data.spans.append(TextSpan(
            text=text, bold=bold, italic=italic,
            underline=underline, strikethrough=strikethrough,
            code=code, color=color, font_size=font_size_str,
            font_family=font_family,
        ))
        return self
