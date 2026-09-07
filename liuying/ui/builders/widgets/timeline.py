"""链式构建时间轴组件的辅助类。"""

from typing import Self

from ...models.widgets.timeline import Timeline, TimelineItem
from ..base import BaseBuilder

__all__ = ["TimelineBuilder"]


class TimelineBuilder(BaseBuilder[Timeline]):
    """链式构建时间轴组件的辅助类。"""

    def __init__(self):
        """初始化空的时间轴构建器。"""
        data_model = Timeline(items=[])
        super().__init__(data_model, template_name="components/widgets/timeline")

    def add_item(
        self,
        timestamp: str,
        title: str,
        content: str,
        *,
        icon: str | None = None,
        color: str | None = None,
    ) -> Self:
        """向时间轴中添加一个事件点。

        参数:
            timestamp: 显示在时间点旁边的时间或标签。
            title: 事件的标题。
            content: 事件的详细描述。
            icon: 可选的自定义图标 SVG 路径。
            color: 可选的节点自定义颜色，覆盖默认主题色。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.items.append(
            TimelineItem(
                timestamp=timestamp,
                title=title,
                content=content,
                icon=icon,
                color=color,
            )
        )
        return self
