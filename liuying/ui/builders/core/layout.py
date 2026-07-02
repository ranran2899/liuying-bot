from typing import Any, Self

from ...models.core.base import RenderableComponent
from ...models.core.layout import LayoutData, LayoutItem
from ..base import BaseBuilder

__all__ = ["LayoutBuilder"]


class LayoutBuilder(BaseBuilder[LayoutData]):
    """将多个UI组件组合成单张图片的链式构建器。"""

    def __init__(self):
        super().__init__(LayoutData(), template_name="")
        self._options: dict[str, Any] = {}

    @classmethod
    def column(
        cls, *, gap: str = "20px", align_items: str = "stretch", **options: Any
    ) -> Self:
        builder = cls()
        builder._template_name = "components/core/layouts/column"
        builder._options = {"gap": gap, "align_items": align_items, **options}
        return builder

    @classmethod
    def row(
        cls, *, gap: str = "10px", align_items: str = "center", **options: Any
    ) -> Self:
        builder = cls()
        builder._template_name = "components/core/layouts/row"
        builder._options = {"gap": gap, "align_items": align_items, **options}
        return builder

    @classmethod
    def grid(cls, columns: int = 2, **options: Any) -> Self:
        builder = cls()
        builder._template_name = "components/core/layouts/grid"
        builder._options = {"columns": columns, **options}
        return builder

    @classmethod
    def hstack(
        cls, components: list["BaseBuilder | RenderableComponent"], **options: Any
    ) -> Self:
        builder = cls.row(**options)
        for component in components:
            builder.add_item(component)
        return builder

    @classmethod
    def vstack(
        cls, components: list["BaseBuilder | RenderableComponent"], **options: Any
    ) -> Self:
        builder = cls.column(**options)
        for component in components:
            builder.add_item(component)
        return builder

    def add_item(
        self,
        component: "BaseBuilder | RenderableComponent",
        metadata: dict[str, Any] | None = None,
    ) -> Self:
        """向布局中添加一个组件项。

        自动调用 Builder 的 build() 方法以应用样式配置。
        """
        component_data = (
            component.build() if isinstance(component, BaseBuilder) else component
        )
        self._data.children.append(
            LayoutItem(component=component_data, metadata=metadata)
        )
        return self

    def add_option(self, key: str, value: Any) -> Self:
        """为布局模板添加一个自定义选项。"""
        self._options[key] = value
        return self

    def build(self) -> LayoutData:
        """构建并返回 LayoutData 模型实例。"""
        if not self._template_name:
            raise ValueError(
                "必须通过工厂方法 (如 LayoutBuilder.column()) 初始化布局类型。"
            )
        self._data.options = self._options
        self._data.layout_type = self._template_name.split("/")[-1]
        return super().build()
