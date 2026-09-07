"""分割线组件数据模型。"""

from typing import Literal

from pydantic import Field

from ..core.base import RenderableComponent

__all__ = ["Divider"]


class Divider(RenderableComponent):
    """分割线组件。"""

    component_type: Literal["divider"] = "divider"
    margin: str = Field("2em 0", description="CSS margin属性，控制分割线上下的间距")
    """CSS margin属性，控制分割线上下的间距"""
    color: str = Field("#f7889c", description="分割线颜色")
    """分割线颜色"""
    style: Literal["solid", "dashed", "dotted"] = Field(
        "solid", description="线条样式"
    )
    """线条样式"""
    thickness: str = Field("1px", description="线条粗细")
    """线条粗细"""

    @property
    def template_name(self) -> str:
        return "components/widgets/divider"
