"""链式构建徽章组件的辅助类。"""

from typing import Literal, Self

from ...models.widgets.badge import Badge
from ..base import BaseBuilder

__all__ = ["BadgeBuilder"]

ColorScheme = Literal["primary", "success", "warning", "error", "info"]
"""组件通用的预设颜色方案。"""


class BadgeBuilder(BaseBuilder[Badge]):
    """链式构建徽章组件的辅助类。"""

    def __init__(self, text: str, color_scheme: ColorScheme = "info"):
        """初始化徽章构建器。

        参数:
            text: 徽章上显示的文本。
            color_scheme: 预设颜色方案。
        """
        data_model = Badge(text=text, color_scheme=color_scheme)
        super().__init__(data_model, template_name="components/widgets/badge")

    def set_color_scheme(self, color_scheme: ColorScheme) -> Self:
        """设置徽章的颜色方案。

        参数:
            color_scheme: 预设颜色方案。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.color_scheme = color_scheme
        return self
