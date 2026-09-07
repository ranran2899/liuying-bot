"""链式构建通用列表的辅助类。"""

from typing import Self

from ...models.core.base import RenderableComponent
from ...models.core.list import ListData, ListItem
from ..base import BaseBuilder, to_component

__all__ = ["ListBuilder"]


class ListBuilder(BaseBuilder[ListData]):
    """链式构建通用列表的辅助类。"""

    def __init__(self, ordered: bool = False):
        """初始化列表构建器。

        参数:
            ordered: 是否为有序列表。
        """
        data_model = ListData(ordered=ordered)
        super().__init__(data_model, template_name="components/core/list")

    def add_item(self, component: "BaseBuilder | RenderableComponent") -> Self:
        """向列表中添加一个项目。

        参数:
            component: 组件模型或构建器。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.items.append(ListItem(component=to_component(component)))
        return self

    def ordered(self, is_ordered: bool = True) -> Self:
        """设置列表是否为有序列表。

        参数:
            is_ordered: True 为有序列表，False 为无序列表。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.ordered = is_ordered
        return self
