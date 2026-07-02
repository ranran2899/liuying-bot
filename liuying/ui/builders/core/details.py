from typing import Any, Self

from ...models.core.details import DetailsData, DetailsItem
from ..base import BaseBuilder


class DetailsBuilder(BaseBuilder[DetailsData]):
    """链式构建描述列表（键值对）的辅助类。"""

    def __init__(self, title: str | None = None):
        data_model = DetailsData(title=title, items=[])
        super().__init__(data_model, template_name="components/core/details")

    def add_item(self, label: str, value: Any) -> Self:
        """向列表中添加一个键值对项目。"""
        self._data.items.append(DetailsItem(label=label, value=str(value)))
        return self
