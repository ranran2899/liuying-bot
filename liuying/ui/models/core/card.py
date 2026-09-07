"""通用卡片组件数据模型。"""

from collections.abc import Iterable

from .base import ContainerComponent, RenderableComponent

__all__ = ["CardData"]


class CardData(ContainerComponent):
    """通用卡片数据模型，可包含头部、内容与尾部。"""

    header: RenderableComponent | None = None
    """卡片的头部内容组件"""
    content: RenderableComponent
    """卡片的主要内容组件"""
    footer: RenderableComponent | None = None
    """卡片的尾部内容组件"""

    @property
    def template_name(self) -> str:
        return "components/core/card"

    def get_children(self) -> Iterable[RenderableComponent]:
        """返回头、内容与尾部子组件供依赖收集。"""
        if self.header:
            yield self.header
        if self.content:
            yield self.content
        if self.footer:
            yield self.footer
