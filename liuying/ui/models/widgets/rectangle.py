"""矩形背景块组件数据模型。"""

from typing import Literal

from pydantic import Field

from ..core.base import RenderableComponent

__all__ = ["Rectangle"]


class Rectangle(RenderableComponent):
    """矩形背景块组件。"""

    component_type: Literal["rectangle"] = "rectangle"
    height: str = Field("50px", description="矩形的高度 (CSS value)")
    """矩形的高度 (CSS value)"""
    background_color: str = Field("#fdf1f5", description="背景颜色")
    """背景颜色"""
    border: str = Field("1px solid #fce4ec", description="CSS border属性")
    """CSS border属性"""
    border_radius: str = Field("8px", description="CSS border-radius属性")
    """CSS border-radius属性"""

    @property
    def template_name(self) -> str:
        return "components/widgets/rectangle"
