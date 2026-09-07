"""提示框组件数据模型。"""

from typing import Literal

from pydantic import Field

from ..core.base import RenderableComponent

__all__ = ["Alert"]


class Alert(RenderableComponent):
    """带样式的提示框组件。"""

    component_type: Literal["alert"] = "alert"
    type: Literal["info", "success", "warning", "error"] = Field(
        default="info", description="提示框的类型，决定了颜色和图标"
    )
    """提示框的类型，决定了颜色和图标"""
    title: str = Field(..., description="提示框的标题")
    """提示框的标题"""
    content: str = Field(..., description="提示框的主要内容")
    """提示框的主要内容"""
    show_icon: bool = Field(default=True, description="是否显示与类型匹配的图标")
    """是否显示与类型匹配的图标"""

    @property
    def template_name(self) -> str:
        return "components/widgets/alert"
