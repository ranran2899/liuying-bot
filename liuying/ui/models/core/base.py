from abc import ABC, abstractmethod
from collections.abc import Awaitable, Iterable
from typing import Any

from pydantic import BaseModel

from liuying.services.renderer.protocols import Renderable
from liuying.utils.pydantic_compat import compat_computed_field, model_dump

__all__ = ["ContainerComponent", "RenderableComponent"]


class RenderableComponent(BaseModel, Renderable, ABC):
    """所有可渲染UI组件的数据模型基类。

    继承自 Pydantic BaseModel 用于数据校验和结构化，同时实现
    Renderable 协议，确保其能够被 RendererService 正确处理。
    """

    _is_standalone_template: bool = False
    inline_style: dict[str, str] | None = None
    component_css: str | None = None
    extra_classes: list[str] | None = None
    variant: str | None = None

    @property
    def template_name(self) -> str:
        raise NotImplementedError(
            "Subclasses must implement the 'template_name' property."
        )

    async def prepare(self) -> None:
        pass

    def get_children(self) -> Iterable["RenderableComponent"]:
        return []

    def get_required_scripts(self) -> list[str]:
        return []

    def get_required_styles(self) -> list[str]:
        return []

    def get_render_data(self) -> dict[str, Any | Awaitable[Any]]:
        return model_dump(
            self, exclude={"inline_style", "component_css", "inline_style_str"}
        )

    @compat_computed_field
    def inline_style_str(self) -> str:
        """将内联样式字典转换为CSS字符串。"""
        if not self.inline_style:
            return ""
        return "; ".join(f"{k}: {v}" for k, v in self.inline_style.items())

    def get_extra_css(self, context: Any) -> str | Awaitable[str]:
        return ""


class ContainerComponent(RenderableComponent, ABC):
    """容器类组件的抽象基类，封装了子组件依赖聚合的通用逻辑。"""

    @abstractmethod
    def get_children(self) -> Iterable[RenderableComponent]:
        raise NotImplementedError

    def _aggregate_deps(self, attr: str) -> list[str]:
        """聚合所有子组件的指定依赖（scripts/styles）。"""
        result = set(getattr(super(), attr)())
        result.update(
            dep
            for child in self.get_children()
            if child
            for dep in getattr(child, attr)()
        )
        return list(result)

    def get_required_scripts(self) -> list[str]:
        return self._aggregate_deps("get_required_scripts")

    def get_required_styles(self) -> list[str]:
        return self._aggregate_deps("get_required_styles")
