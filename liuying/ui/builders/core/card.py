"""链式构建通用卡片容器的辅助类。"""

from typing import Self

from ...models.core.base import RenderableComponent
from ...models.core.card import CardData
from ..base import BaseBuilder, to_component

__all__ = ["CardBuilder"]


class CardBuilder(BaseBuilder[CardData]):
    """链式构建通用卡片容器的辅助类。"""

    def __init__(self, content: "RenderableComponent | BaseBuilder"):
        """初始化卡片构建器。

        参数:
            content: 卡片的主要内容组件，可为组件模型或构建器。
        """
        data_model = CardData(content=to_component(content))
        super().__init__(data_model, template_name="components/core/card")

    def set_header(self, header: "RenderableComponent | BaseBuilder") -> Self:
        """设置卡片的头部组件。

        参数:
            header: 头部组件，可为组件模型或构建器。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.header = to_component(header)
        return self

    def set_footer(self, footer: "RenderableComponent | BaseBuilder") -> Self:
        """设置卡片的尾部组件。

        参数:
            footer: 尾部组件，可为组件模型或构建器。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.footer = to_component(footer)
        return self
