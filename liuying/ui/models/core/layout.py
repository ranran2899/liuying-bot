"""布局组件数据模型，支持 column/row/grid 等布局类型。"""

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, Field

from .base import ContainerComponent, RenderableComponent

__all__ = ["LayoutData", "LayoutItem"]


class LayoutItem(BaseModel):
    """布局中的单个项目。"""

    component: RenderableComponent = Field(..., description="要渲染的组件")
    """要渲染的组件的数据模型"""
    metadata: dict[str, Any] | None = Field(
        None, description="传递给模板的额外元数据"
    )
    """传递给模板的额外元数据"""


class LayoutData(ContainerComponent):
    """布局组件数据模型。"""

    style_name: str | None = None
    """应用于布局容器的样式名称"""
    layout_type: str = "column"
    """布局类型 (如 'column', 'row', 'grid')"""
    children: list[LayoutItem] = Field(
        default_factory=list, description="要布局的项目列表"
    )
    """要布局的项目列表"""
    options: dict[str, Any] = Field(
        default_factory=dict, description="传递给模板的选项"
    )
    """传递给模板的选项"""

    @property
    def template_name(self) -> str:
        return f"components/core/layouts/{self.layout_type}"

    def get_extra_css(self, context: Any) -> str:
        """聚合自身与所有子组件的自定义 CSS。

        参数:
            context: 当前渲染上下文对象。

        返回:
            str: 拼接后的 CSS 文本，无自定义样式时返回空字符串。
        """
        all_css = [
            css for item in self.children
            if item.component and (css := item.component.component_css)
        ]
        if self.component_css:
            all_css.insert(0, self.component_css)
        return "\n".join(all_css)

    def get_children(self) -> Iterable[RenderableComponent]:
        for item in self.children:
            yield item.component
