"""将多个 UI 组件组合成单张图片的链式布局构建器。"""

from typing import Any, Self

from ...models.core.base import RenderableComponent
from ...models.core.layout import LayoutData, LayoutItem
from ..base import BaseBuilder, to_component

__all__ = ["LayoutBuilder"]


class LayoutBuilder(BaseBuilder[LayoutData]):
    """将多个 UI 组件组合成单张图片的链式构建器。

    必须通过 column()/row()/grid() 工厂方法创建以确定布局类型。
    """

    def __init__(self):
        """初始化空布局构建器，需调用工厂方法设置布局类型。"""
        super().__init__(LayoutData(), template_name="")
        self._options: dict[str, Any] = {}

    @classmethod
    def column(
        cls, *, gap: str = "20px", align_items: str = "stretch", **options: Any
    ) -> Self:
        """创建垂直列布局构建器。

        参数:
            gap: 子项之间的间距（CSS 值）。
            align_items: 子项的交叉轴对齐方式。
            **options: 传递给布局模板的其他选项（如 padding）。

        返回:
            Self: 配置好的布局构建器。
        """
        builder = cls()
        builder._template_name = "components/core/layouts/column"
        builder._options = {"gap": gap, "align_items": align_items, **options}
        return builder

    @classmethod
    def row(
        cls, *, gap: str = "10px", align_items: str = "center", **options: Any
    ) -> Self:
        """创建水平行布局构建器。

        参数:
            gap: 子项之间的间距（CSS 值）。
            align_items: 子项的交叉轴对齐方式。
            **options: 传递给布局模板的其他选项（如 padding）。

        返回:
            Self: 配置好的布局构建器。
        """
        builder = cls()
        builder._template_name = "components/core/layouts/row"
        builder._options = {"gap": gap, "align_items": align_items, **options}
        return builder

    @classmethod
    def grid(cls, columns: int = 2, **options: Any) -> Self:
        """创建网格布局构建器。

        参数:
            columns: 网格列数。
            **options: 传递给布局模板的其他选项（如 gap/padding）。

        返回:
            Self: 配置好的布局构建器。
        """
        builder = cls()
        builder._template_name = "components/core/layouts/grid"
        builder._options = {"columns": columns, **options}
        return builder

    @classmethod
    def hstack(
        cls, components: list["BaseBuilder | RenderableComponent"], **options: Any
    ) -> Self:
        """用水平行布局组合一组组件。

        参数:
            components: 组件模型或构建器的列表。
            **options: 传递给行布局的选项。

        返回:
            Self: 已添加全部组件的布局构建器。
        """
        builder = cls.row(**options)
        for component in components:
            builder.add_item(component)
        return builder

    @classmethod
    def vstack(
        cls, components: list["BaseBuilder | RenderableComponent"], **options: Any
    ) -> Self:
        """用垂直列布局组合一组组件。

        参数:
            components: 组件模型或构建器的列表。
            **options: 传递给列布局的选项。

        返回:
            Self: 已添加全部组件的布局构建器。
        """
        builder = cls.column(**options)
        for component in components:
            builder.add_item(component)
        return builder

    def add_item(
        self,
        component: "BaseBuilder | RenderableComponent",
        metadata: dict[str, Any] | None = None,
    ) -> Self:
        """向布局中添加一个组件项，构建器会自动 build。

        参数:
            component: 组件模型或构建器。
            metadata: 传递给布局模板的额外元数据。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.children.append(
            LayoutItem(component=to_component(component), metadata=metadata)
        )
        return self

    def add_option(self, key: str, value: Any) -> Self:
        """为布局模板添加一个自定义选项。

        参数:
            key: 选项键名。
            value: 选项值。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._options[key] = value
        return self

    def build(self) -> LayoutData:
        """构建并返回 LayoutData 模型实例。

        把选项与布局类型写入数据模型。

        返回:
            LayoutData: 配置完成的数据模型实例。

        异常:
            ValueError: 未通过工厂方法初始化布局类型时抛出。
        """
        if not self._template_name:
            raise ValueError(
                "必须通过工厂方法 (如 LayoutBuilder.column()) 初始化布局类型。"
            )
        self._data.options = self._options
        self._data.layout_type = self._template_name.split("/")[-1]
        return super().build()
