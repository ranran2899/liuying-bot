"""链式构建统计卡片（KPI Card）的辅助类。"""

from typing import Literal, Self

from ...models.widgets.kpi_card import KpiCard
from ..base import BaseBuilder

__all__ = ["KpiCardBuilder"]


class KpiCardBuilder(BaseBuilder[KpiCard]):
    """链式构建统计卡片（KPI Card）的辅助类。"""

    def __init__(self, label: str, value: object):
        """初始化统计卡片构建器。

        参数:
            label: 指标的标签或名称。
            value: 指标的主要数值。
        """
        data_model = KpiCard(label=label, value=value)
        super().__init__(data_model, template_name="components/widgets/kpi_card")

    def with_unit(self, unit: str) -> Self:
        """设置数值的单位。

        参数:
            unit: 单位文本，显示在数值右侧。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.unit = unit
        return self

    def with_change(
        self,
        change: str,
        type: Literal["positive", "negative", "neutral"] = "neutral",
    ) -> Self:
        """设置与上一周期的变化率。

        参数:
            change: 变化描述文本，如 '+15%'。
            type: 变化类型，决定颜色（正/负/中性）。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.change = change
        self._data.change_type = type
        return self

    def with_icon(self, svg_path: str) -> Self:
        """设置卡片图标。

        参数:
            svg_path: SVG path data，渲染在标签左侧。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.icon_svg = svg_path
        return self
