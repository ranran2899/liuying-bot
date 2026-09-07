"""UI 构建器通用基类与构建辅助函数。"""

from pathlib import Path
from typing import Self

from pydantic import BaseModel

from ..models.core.base import RenderableComponent


def to_component(
    component: "RenderableComponent | BaseBuilder",
) -> RenderableComponent:
    """接受组件模型或构建器，统一转换为数据模型。

    参数:
        component: 组件数据模型，或调用 build() 后返回数据模型的构建器。

    返回:
        RenderableComponent: 转换后的数据模型实例。
    """
    if isinstance(component, BaseBuilder):
        return component.build()
    return component


def resolve_image_src(content: str | Path) -> str:
    """把本地路径或 base64 内容解析为可用的图片 src。

    参数:
        content: 图片来源，支持文件路径与 `base64://` 前缀的数据。

    返回:
        str: 可直接用于 <img src> 的字符串
            （文件 URI / data URI / 原始字符串）。
    """
    if isinstance(content, Path):
        return content.absolute().as_uri()
    if content.startswith("base64://"):
        return f"data:image/png;base64,{content.removeprefix('base64://')}"
    return content


class BaseBuilder[T_DataModel: BaseModel]:
    """所有 UI 构建器的通用基类。

    以链式 API 配置组件数据模型与通用样式字段，build() 时统一写入。
    """

    def __init__(self, data_model: T_DataModel, template_name: str):
        """初始化构建器。

        参数:
            data_model: 构建器持有的数据模型实例。
            template_name: 组件对应的模板路径。
        """
        self._data: T_DataModel = data_model
        self._style_name: str | None = None
        self._template_name = template_name
        self._inline_style: dict | None = None
        self._component_css: str | None = None
        self._variant: str | None = None
        self._extra_classes: list[str] = []

    @property
    def data(self) -> T_DataModel:
        """当前构建器持有的数据模型。

        返回:
            T_DataModel: 数据模型实例。
        """
        return self._data

    def with_style(self, style_name: str) -> Self:
        """为组件应用一个特定的样式。

        参数:
            style_name: 样式名称。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._style_name = style_name
        return self

    def with_inline_style(self, style: dict[str, str]) -> Self:
        """为组件的根元素应用动态的内联样式。

        参数:
            style: CSS 属性到值的映射。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._inline_style = style
        return self

    def with_variant(self, variant_name: str) -> Self:
        """为组件应用一个特定的变体/皮肤。

        参数:
            variant_name: 变体名称，对应组件目录下的主题子目录。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._variant = variant_name
        return self

    def with_component_css(self, css: str) -> Self:
        """向页面注入一段自定义的 CSS 样式字符串。

        参数:
            css: 自定义 CSS 文本。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._component_css = css
        return self

    def with_classes(self, *class_names: str) -> Self:
        """为组件的根元素添加一个或多个 CSS 工具类。

        参数:
            *class_names: CSS 类名列表。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._extra_classes.extend(class_names)
        return self

    def build(self) -> T_DataModel:
        """构建并返回配置好的数据模型。

        把链式调用累积的样式字段写入数据模型（模型存在对应字段时）。

        返回:
            T_DataModel: 配置完成的数据模型实例。
        """
        style_attrs: list[tuple[str, object]] = [
            ("style_name", self._style_name),
            ("inline_style", self._inline_style),
            ("component_css", self._component_css),
            ("variant", self._variant),
            ("extra_classes", self._extra_classes or None),
        ]
        for attr_name, attr_value in style_attrs:
            if attr_value and hasattr(self._data, attr_name):
                setattr(self._data, attr_name, attr_value)
        return self._data
