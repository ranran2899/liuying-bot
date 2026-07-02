from typing import Self

from ...models.core.base import RenderableComponent
from ...models.core.list import ListData, ListItem
from ..base import BaseBuilder


class ListBuilder(BaseBuilder[ListData]):
    """链式构建通用列表的辅助类。"""

    def __init__(self, ordered: bool = False):
        data_model = ListData(ordered=ordered)
        super().__init__(data_model, template_name="components/core/list")

    def add_item(self, component: "BaseBuilder | RenderableComponent") -> Self:
        """向列表中添加一个项目。"""
        component_data = (
            component.build() if isinstance(component, BaseBuilder) else component
        )
        self._data.items.append(ListItem(component=component_data))
        return self

    def ordered(self, is_ordered: bool = True) -> Self:
        """设置列表是否为有序列表。"""
        self._data.ordered = is_ordered
        return self
