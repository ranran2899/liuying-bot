"""链式构建提示/标注框组件的辅助类。"""

from typing import Literal, Self

from ...models.widgets.alert import Alert
from ..base import BaseBuilder

__all__ = ["AlertBuilder"]


class AlertBuilder(BaseBuilder[Alert]):
    """链式构建提示/标注框组件的辅助类。"""

    def __init__(
        self,
        title: str,
        content: str,
        type: Literal["info", "success", "warning", "error"] = "info",
    ):
        """初始化提示框构建器。

        参数:
            title: 提示框标题。
            content: 提示框内容。
            type: 提示框类型，决定配色与图标。
        """
        data_model = Alert(title=title, content=content, type=type)
        super().__init__(data_model, template_name="components/widgets/alert")

    def hide_icon(self) -> Self:
        """隐藏提示框的默认图标。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.show_icon = False
        return self
