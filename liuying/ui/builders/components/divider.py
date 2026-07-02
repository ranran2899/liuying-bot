from typing import Literal, Self

from ...models.components.divider import Divider
from ..base import BaseBuilder


class DividerBuilder(BaseBuilder[Divider]):
    """链式构建分割线组件的辅助类。"""

    def __init__(
        self,
        margin: str = "2em 0",
        color: str = "#f7889c",
        style: Literal["solid", "dashed", "dotted"] = "solid",
        thickness: str = "1px",
    ):
        data_model = Divider(
            margin=margin, color=color, style=style, thickness=thickness
        )
        super().__init__(data_model, template_name="components/widgets/divider")

    def set_margin(self, margin: str) -> Self:
        self._data.margin = margin
        return self

    def set_color(self, color: str) -> Self:
        self._data.color = color
        return self

    def set_style(
        self, style: Literal["solid", "dashed", "dotted"]
    ) -> Self:
        self._data.style = style
        return self

    def set_thickness(self, thickness: str) -> Self:
        self._data.thickness = thickness
        return self
