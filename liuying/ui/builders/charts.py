"""ECharts 图表构建器与便捷工厂函数。"""

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
    """统一的 ECharts 图表构建器，提供链式 API 设置 option。"""

    def __init__(self, template_name: str, title: str):
        """初始化图表构建器。

        参数:
            template_name: 图表组件的模板路径，如 "components/charts/bar_chart"。
            title: 图表初始标题文本。
        """
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
        """设置图表标题与水平位置。

        参数:
            text: 标题文本。
            left: 标题水平对齐位置。

        返回:
            Self: 构建器自身，支持链式调用。
        """
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
        """设置绘图网格边距。

        参数:
            left: 网格距容器左侧的距离。
            right: 网格距容器右侧的距离。
            top: 网格距容器顶部的距离。
            bottom: 网格距容器底部的距离。
            contain_label: 网格是否包含坐标轴标签。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.grid_model = EChartsGrid(
            left=left,
            right=right,
            top=top,
            bottom=bottom,
            containLabel=contain_label,
        )
        return self

    def set_tooltip(self, trigger: Literal["item", "axis", "none"]) -> Self:
        """设置提示框触发方式。

        参数:
            trigger: 触发类型，item/axis/none。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.tooltip_model = EChartsTooltip(trigger=trigger)
        return self

    def set_axis(
        self, attr: str, type: Literal["category", "value", "time", "log"],
        data: list[Any] | None = None, show: bool = True,
    ) -> Self:
        """设置坐标轴（attr 为 x_axis_model 或 y_axis_model）。

        参数:
            attr: 目标模型属性名。
            type: 坐标轴类型。
            data: 类目轴的类目数据。
            show: 是否显示坐标轴。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        axis = EChartsAxis(type=type, data=data, show=show)
        setattr(self._data, attr, axis)
        return self

    def set_x_axis(
        self,
        type: Literal["category", "value", "time", "log"],
        data: list[Any] | None = None,
        show: bool = True,
    ) -> Self:
        """设置 X 轴。

        参数:
            type: 坐标轴类型。
            data: 类目轴的类目数据。
            show: 是否显示坐标轴。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        return self.set_axis("x_axis_model", type, data, show)

    def set_y_axis(
        self,
        type: Literal["category", "value", "time", "log"],
        data: list[Any] | None = None,
        show: bool = True,
    ) -> Self:
        """设置 Y 轴。

        参数:
            type: 坐标轴类型。
            data: 类目轴的类目数据。
            show: 是否显示坐标轴。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        return self.set_axis("y_axis_model", type, data, show)

    def add_series(
        self, type: str, data: list[Any], name: str | None = None, **kwargs: Any
    ) -> Self:
        """追加一个数据系列。

        参数:
            type: 系列类型，如 bar/line/pie/radar。
            data: 系列数据。
            name: 系列名称，用于图例与提示框。
            **kwargs: 其他 ECharts 系列配置项（如 smooth、label 等）。

        返回:
            Self: 构建器自身，支持链式调用。
        """
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
        """设置图例。

        参数:
            data: 图例项（系列名称）列表。
            orient: 图例排布方向。
            left: 图例距容器左侧的距离。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.legend_model = {"data": data, "orient": orient, "left": left}
        return self

    def set_option(self, key: str, value: Any) -> Self:
        """设置 ECharts option 中的原始键值对，覆盖同名配置。

        参数:
            key: option 键名，如 "radar"、"color"。
            value: 对应的配置值。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.raw_options[key] = value
        return self

    def set_background_image(self, image_name: str) -> Self:
        """为图表设置背景图片。

        参数:
            image_name: 主题 assets 下 ui/background/ 目录中的图片名。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.background_image = image_name
        return self


def bar_chart(
    title: str,
    items: list[tuple[str, int | float]],
    direction: Literal["horizontal", "vertical"] = "horizontal",
) -> EChartsBuilder:
    """便捷工厂函数：创建一个柱状图构建器。

    参数:
        title: 图表标题。
        items: (类别名, 数值) 的二元组列表。
        direction: 柱状图方向，horizontal 为横向条形图。

    返回:
        EChartsBuilder: 配置好坐标轴与系列的构建器。
    """
    builder = EChartsBuilder("components/charts/bar_chart", title)
    categories, values = zip(*items) if items else ([], [])
    categories, values = list(categories), list(values)

    match direction:
        case "horizontal":
            builder.set_x_axis(type="value")
            builder.set_y_axis(type="category", data=categories)
            builder.add_series(type="bar", data=values)
        case "vertical":
            builder.set_x_axis(type="category", data=categories)
            builder.set_y_axis(type="value")
            builder.add_series(type="bar", data=values)
    return builder


def pie_chart(title: str, items: list[tuple[str, int | float]]) -> EChartsBuilder:
    """便捷工厂函数：创建一个饼图构建器。

    参数:
        title: 图表标题，同时作为系列名。
        items: (名称, 数值) 的二元组列表。

    返回:
        EChartsBuilder: 配置好图例与系列的构建器。
    """
    builder = EChartsBuilder("components/charts/pie_chart", title)
    builder.set_legend(data=[name for name, _ in items])
    builder.add_series(
        name=title,
        type="pie",
        data=[{"name": name, "value": value} for name, value in items],
    )
    return builder


def line_chart(
    title: str, categories: list[str], series: list[dict[str, Any]]
) -> EChartsBuilder:
    """便捷工厂函数：创建一个折线图构建器。

    参数:
        title: 图表标题。
        categories: X 轴类目列表。
        series: 系列配置列表，每项含 name/data，可选 smooth。

    返回:
        EChartsBuilder: 配置好坐标轴与系列的构建器。
    """
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
    title: str,
    indicators: list[tuple[str, int | float]],
    series: list[dict[str, Any]],
) -> EChartsBuilder:
    """便捷工厂函数：创建一个雷达图构建器。

    参数:
        title: 图表标题。
        indicators: (指标名, 最大值) 的二元组列表。
        series: 系列配置列表，每项含 name/data。

    返回:
        EChartsBuilder: 配置好图例、radar 指标与系列的构建器。
    """
    builder = EChartsBuilder("components/charts/radar_chart", title)
    builder.set_legend(data=[s.get("name", "") for s in series])
    builder.set_option(
        "radar",
        {"indicator": [{"name": n, "max": m} for n, m in indicators]},
    )
    builder.add_series(type="radar", data=series)
    return builder
