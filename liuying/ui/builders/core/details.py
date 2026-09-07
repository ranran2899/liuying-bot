"""链式构建描述列表（键值对）的辅助类。"""

from typing import Any, Self

from ...models.core.details import DetailsData, DetailsItem
from ..base import BaseBuilder

__all__ = ["DetailsBuilder"]


class DetailsBuilder(BaseBuilder[DetailsData]):
    """链式构建描述列表（键值对）的辅助类。"""

    def __init__(self, title: str | None = None):
        """初始化描述列表构建器。

        参数:
            title: 列表的可选标题。
        """
        data_model = DetailsData(title=title, items=[])
        super().__init__(data_model, template_name="components/core/details")

    def add_item(self, label: str, value: Any) -> Self:
        """向列表中添加一个键值对项目。

        参数:
            label: 项目的标签/键。
            value: 项目的值，非字符串会被转换为 str。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.items.append(DetailsItem(label=label, value=str(value)))
        return self
