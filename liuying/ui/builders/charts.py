from typing import Any, Literal, Self

from ..models.charts import (
    EChartsAxis,
    EChartsData,
    EChartsGrid,
    EChartsSeries,
    EChartsTitle,
    EChartsTooltip,
)
from .base import BaseBuilder


class EChartsBuilder(BaseBuilder[EChartsData]):
    """统一的 ECharts 图表构建器，提供链式API设置 option。"""

    def __init__(self, template_name: str, title: str):
        model = EChartsData(
            template_path=template_name,
            title=EChartsTitle(text=title),
            grid=None,
            tooltip=None,
            xAxis=None,
            yAxis=None,
            legend=None,
            background_image=None,
        )
        super().__init__(model, template_name=template_name)

    def set_title(
        self, text: str, left: Literal["left", "center", "right"] = "center"
    ) -> Self:
        self._data.title_model = EChartsTitle(text=text, left=left)
        return self

    def set_grid(
        self,
        left: str | None = None,
        right: str | None = None,
        top: str | None = None,
        bottom: str | None = None,
        contain_label: bool = True,
    ) -> Self:
        self._data.grid_model = EChartsGrid(
            left=left, right=right, top=top,
            bottom=bottom, containLabel=contain_label,
        )
        return self

    def set_tooltip(self, trigger: Literal["item", "axis", "none"]) -> Self:
        self._data.tooltip_model = EChartsTooltip(trigger=trigger)
        return self

    def set_x_axis(
        self,
        type: Literal["category", "value", "time", "log"],
        data: list[Any] | None = None,
        show: bool = True,
    ) -> Self:
        self._data.x_axis_model = EChartsAxis(type=type, data=data, show=show)
        return self

    def set_y_axis(
        self,
        type: Literal["category", "value", "time", "log"],
        data: list[Any] | None = None,
        show: bool = True,
    ) -> Self:
        self._data.y_axis_model = EChartsAxis(type=type, data=data, show=show)
        return self

    def add_series(
        self, type: str, data: list[Any], name: str | None = None, **kwargs: Any
    ) -> Self:
        self._data.series_models.append(
            EChartsSeries(type=type, data=data, name=name, **kwargs)
        )
        return self

    def set_legend(
        self,
        data: list[str],
        orient: Literal["horizontal", "vertical"] = "horizontal",
        left: str = "auto",
    ) -> Self:
        self._data.legend_model = {"data": data, "orient": orient, "left": left}
        return self

    def set_option(self, key: str, value: Any) -> Self:
        """设置 ECharts option 中的原始键值对，覆盖同名配置。"""
        self._data.raw_options[key] = value
        return self

    def set_background_image(self, image_name: str) -> Self:
        """为横向柱状图设置背景图片。"""
        self._data.background_image = image_name
        return self


def bar_chart(
    title: str,
    items: list[tuple[str, int | float]],
    direction: Literal["horizontal", "vertical"] = "horizontal",
) -> EChartsBuilder:
    """便捷工厂函数：创建一个柱状图构建器。"""
    builder = EChartsBuilder("components/charts/bar_chart", title)
    categories, values = zip(*items) if items else ([], [])

    match direction:
        case "horizontal":
            builder.set_x_axis(type="value")
            builder.set_y_axis(type="category", data=list(categories))
            builder.add_series(type="bar", data=list(values))
        case "vertical":
            builder.set_x_axis(type="category", data=list(categories))
            builder.set_y_axis(type="value")
            builder.add_series(type="bar", data=list(values))

    return builder


def pie_chart(title: str, items: list[tuple[str, int | float]]) -> EChartsBuilder:
    """便捷工厂函数：创建一个饼图构建器。"""
    builder = EChartsBuilder("components/charts/pie_chart", title)
    data = [{"name": name, "value": value} for name, value in items]
    legend_data = [name for name, _ in items]

    builder.set_legend(data=legend_data)
    builder.add_series(name=title, type="pie", data=data)
    return builder


def line_chart(
    title: str, categories: list[str], series: list[dict[str, Any]]
) -> EChartsBuilder:
    """便捷工厂函数：创建一个折线图构建器。"""
    builder = EChartsBuilder("components/charts/line_chart", title)

    builder.set_x_axis(type="category", data=categories)
    builder.set_y_axis(type="value")
    for s in series:
        builder.add_series(
            type="line",
            name=s.get("name", ""),
            data=s.get("data", []),
            smooth=s.get("smooth", False),
        )
    return builder


def radar_chart(
    title: str, indicators: list[tuple[str, int | float]],
    series: list[dict[str, Any]],
) -> EChartsBuilder:
    """便捷工厂函数：创建一个雷达图构建器。"""
    builder = EChartsBuilder("components/charts/radar_chart", title)
    legend_data = [s.get("name", "") for s in series]
    radar_indicators = [
        {"name": name, "max": max_val} for name, max_val in indicators
    ]

    builder.set_legend(data=legend_data)
    builder.set_option("radar", {"indicator": radar_indicators})
    builder.add_series(type="radar", data=series)
    return builder
