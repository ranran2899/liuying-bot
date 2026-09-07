"""ECharts 图表数据模型。

将链式构建的模型序列化为 ECharts option 字典。
"""

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from liuying.utils.pydantic_compat import model_dump

from .core.base import RenderableComponent

__all__ = [
    "BaseChartData",
    "EChartsAxis",
    "EChartsData",
    "EChartsGrid",
    "EChartsSeries",
    "EChartsTitle",
    "EChartsTooltip",
]


class EChartsTitle(BaseModel):
    """图表标题配置。"""

    text: str
    left: Literal["left", "center", "right"] = "center"


class EChartsAxis(BaseModel):
    """坐标轴配置。"""

    type: Literal["category", "value", "time", "log"]
    data: list[Any] | None = None
    show: bool = True


class EChartsSeries(BaseModel):
    """数据系列配置。"""

    type: str
    data: list[Any]
    name: str | None = None
    label: dict[str, Any] | None = None
    itemStyle: dict[str, Any] | None = None
    barMaxWidth: int | None = None
    smooth: bool | None = None


class EChartsTooltip(BaseModel):
    """提示框配置。"""

    trigger: Literal["item", "axis", "none"] = "item"


class EChartsGrid(BaseModel):
    """绘图网格配置。"""

    left: str | None = None
    right: str | None = None
    top: str | None = None
    bottom: str | None = None
    containLabel: bool = True


class BaseChartData(RenderableComponent, ABC):
    """所有图表数据模型的基类。"""

    style_name: str | None = None
    chart_id: str = Field(default_factory=lambda: f"chart-{uuid4().hex[:8]}")
    echarts_options: dict[str, Any] | None = None

    @abstractmethod
    def build_option(self) -> dict[str, Any]:
        """构建 ECharts 的 option 字典。

        返回:
            dict[str, Any]: 可直接传给 echarts.setOption 的配置字典。
        """
        raise NotImplementedError

    def get_render_data(self) -> dict[str, Any]:
        """在渲染数据中附带构建好的 option。

        返回:
            dict[str, Any]: 模型数据与 option 键的合并字典。
        """
        dumped = model_dump(self, exclude={"template_path"})
        dumped["option"] = self.build_option()
        return dumped

    def get_required_scripts(self) -> list[str]:
        """返回图表组件依赖的运行时脚本。

        返回:
            list[str]: 固定为 ["js/echarts.min.js"]。
        """
        return ["js/echarts.min.js"]


class EChartsData(BaseChartData):
    """统一的 ECharts 图表数据模型。"""

    template_path: str = Field(..., exclude=True)
    title_model: EChartsTitle | None = Field(None, alias="title")
    grid_model: EChartsGrid | None = Field(None, alias="grid")
    tooltip_model: EChartsTooltip | None = Field(None, alias="tooltip")
    x_axis_model: EChartsAxis | None = Field(None, alias="xAxis")
    y_axis_model: EChartsAxis | None = Field(None, alias="yAxis")
    series_models: list[EChartsSeries] = Field(default_factory=list, alias="series")
    legend_model: dict[str, Any] | None = Field(default_factory=dict, alias="legend")
    raw_options: dict[str, Any] = Field(default_factory=dict)
    background_image: str | None = None

    # option 键到模型属性的映射
    _KEY_MAP: ClassVar[dict[str, str]] = {
        "title": "title_model",
        "grid": "grid_model",
        "tooltip": "tooltip_model",
        "xAxis": "x_axis_model",
        "yAxis": "y_axis_model",
        "series": "series_models",
        "legend": "legend_model",
    }

    def build_option(self) -> dict[str, Any]:
        """把各子模型序列化后合并为完整的 option 字典。

        返回:
            dict[str, Any]: 各子模型按 _KEY_MAP 展开的配置，
                最后叠加 raw_options 中的原始键值对。
        """
        option: dict[str, Any] = {}
        for echarts_key, model_attr in self._KEY_MAP.items():
            value = getattr(self, model_attr, None)
            if not value:
                continue
            match value:
                case list():
                    option[echarts_key] = [
                        model_dump(m, exclude_none=True) for m in value
                    ]
                case BaseModel():
                    option[echarts_key] = model_dump(value, exclude_none=True)
                case _:
                    option[echarts_key] = value
        option.update(self.raw_options)
        return option

    @property
    def title(self) -> str:
        """返回图表标题文本。

        返回:
            str: 标题文本，未设置标题时返回空字符串。
        """
        return self.title_model.text if self.title_model else ""

    @property
    def template_name(self) -> str:
        """返回图表组件的模板路径。

        返回:
            str: 初始化时传入的模板路径。
        """
        return self.template_path
