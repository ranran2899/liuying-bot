"""链式构建进度条组件的辅助类。"""

from typing import Literal, Self

from ...models.widgets.progress_bar import ProgressBar
from ..base import BaseBuilder

__all__ = ["ProgressBarBuilder"]

ColorScheme = Literal["primary", "success", "warning", "error", "info"]
"""组件通用的预设颜色方案。"""


class ProgressBarBuilder(BaseBuilder[ProgressBar]):
    """链式构建进度条组件的辅助类。"""

    def __init__(
        self,
        progress: float,
        label: str | None = None,
        color_scheme: ColorScheme = "primary",
        animated: bool = False,
    ):
        """初始化进度条构建器。

        参数:
            progress: 进度百分比，取值 0-100。
            label: 显示在进度条上的可选文本。
            color_scheme: 预设颜色方案。
            animated: 是否显示条纹动画。
        """
        data_model = ProgressBar(
            progress=progress,
            label=label,
            color_scheme=color_scheme,
            animated=animated,
        )
        super().__init__(
            data_model, template_name="components/widgets/progress_bar"
        )

    def set_label(self, label: str) -> Self:
        """设置进度条上显示的文本。

        参数:
            label: 标签文本。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.label = label
        return self

    def set_color_scheme(self, color_scheme: ColorScheme) -> Self:
        """设置进度条的颜色方案。

        参数:
            color_scheme: 预设颜色方案。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.color_scheme = color_scheme
        return self

    def set_animated(self, animated: bool = True) -> Self:
        """设置进度条是否显示动画效果。

        参数:
            animated: 是否显示条纹动画。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.animated = animated
        return self
