from typing import Generic, Self, TypeVar

from pydantic import BaseModel

T_DataModel = TypeVar("T_DataModel", bound=BaseModel)


class BaseBuilder(Generic[T_DataModel]):
    """所有UI构建器的通用基类。

    实现Builder设计模式，提供流畅的链式调用API来创建和配置
    UI组件的数据模型，以及通用的样式化方法。

    参数:
        T_DataModel: 与此构建器关联的 Pydantic 数据模型类型。
    """

    def __init__(self, data_model: T_DataModel, template_name: str):
        self._data: T_DataModel = data_model
        self._style_name: str | None = None
        self._template_name = template_name
        self._inline_style: dict | None = None
        self._component_css: str | None = None
        self._variant: str | None = None
        self._extra_classes: list[str] = []

    @property
    def data(self) -> T_DataModel:
        return self._data

    def with_style(self, style_name: str) -> Self:
        """为组件应用一个特定的样式。"""
        self._style_name = style_name
        return self

    def with_inline_style(self, style: dict[str, str]) -> Self:
        """为组件的根元素应用动态的内联样式。"""
        self._inline_style = style
        return self

    def with_variant(self, variant_name: str) -> Self:
        """为组件应用一个特定的变体/皮肤。"""
        self._variant = variant_name
        return self

    def with_component_css(self, css: str) -> Self:
        """向页面注入一段自定义的CSS样式字符串。"""
        self._component_css = css
        return self

    def with_classes(self, *class_names: str) -> Self:
        """为组件的根元素添加一个或多个CSS工具类。"""
        self._extra_classes.extend(class_names)
        return self

    def build(self) -> T_DataModel:
        """构建并返回配置好的数据模型。"""
        style_attrs = {
            "style_name": self._style_name,
            "inline_style": self._inline_style,
            "component_css": self._component_css,
            "variant": self._variant,
            "extra_classes": self._extra_classes or None,
        }
        for attr_name, attr_value in style_attrs.items():
            if attr_value and hasattr(self._data, attr_name):
                setattr(self._data, attr_name, attr_value)
        return self._data
