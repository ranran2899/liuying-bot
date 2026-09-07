"""链式构建分割线组件的辅助类。"""

from typing import Literal, Self

from ...models.widgets.divider import Divider
from ..base import BaseBuilder

__all__ = ["DividerBuilder"]


class DividerBuilder(BaseBuilder[Divider]):
    """链式构建分割线组件的辅助类。"""

    def __init__(
        self,
        margin: str = "2em 0",
        color: str = "#f7889c",
        style: Literal["solid", "dashed", "dotted"] = "solid",
        thickness: str = "1px",
    ):
        """初始化分割线构建器。

        参数:
            margin: 分割线上下间距（CSS margin 值）。
            color: 分割线颜色（CSS 颜色值）。
            style: 线条样式（solid/dashed/dotted）。
            thickness: 线条粗细（CSS 值）。
        """
        data_model = Divider(
            margin=margin, color=color, style=style, thickness=thickness
        )
        super().__init__(data_model, template_name="components/widgets/divider")

    def set_margin(self, margin: str) -> Self:
        """设置分割线上下间距。

        参数:
            margin: CSS margin 值。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.margin = margin
        return self

    def set_color(self, color: str) -> Self:
        """设置分割线颜色。

        参数:
            color: CSS 颜色值。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.color = color
        return self

    def set_style(
        self, style: Literal["solid", "dashed", "dotted"]
    ) -> Self:
        """设置线条样式。

        参数:
            style: 线条样式（solid/dashed/dotted）。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.style = style
        return self

    def set_thickness(self, thickness: str) -> Self:
        """设置线条粗细。

        参数:
            thickness: CSS 值，如 "1px"、"2px"。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.thickness = thickness
        return self
