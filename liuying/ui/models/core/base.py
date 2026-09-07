"""UI 组件数据模型基类。

定义所有可渲染组件的公共字段、模板钩子与依赖聚合逻辑。
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Iterable
from typing import Any

from pydantic import BaseModel

from liuying.services.renderer.protocols import Renderable
from liuying.utils.pydantic_compat import compat_computed_field, model_dump

__all__ = ["ContainerComponent", "RenderableComponent"]


class RenderableComponent(BaseModel, Renderable, ABC):
    """所有可渲染 UI 组件的数据模型基类。

    继承 Pydantic BaseModel 提供数据校验，同时实现 Renderable 协议，
    确保能被渲染服务统一处理。
    """

    _is_standalone_template: bool = False
    inline_style: dict[str, str] | None = None
    component_css: str | None = None
    extra_classes: list[str] | None = None
    variant: str | None = None

    @property
    def template_name(self) -> str:
        """返回组件对应的模板路径。

        返回:
            str: 模板路径，子类必须覆写。

        异常:
            NotImplementedError: 子类未实现时抛出。
        """
        raise NotImplementedError("子类必须实现 template_name 属性。")

    async def prepare(self) -> None:
        """渲染前的异步预处理钩子，默认无操作。"""

    def get_children(self) -> Iterable["RenderableComponent"]:
        """返回直接子组件。

        返回:
            Iterable[RenderableComponent]: 空元组，叶子组件无需覆写。
        """
        return ()

    def get_required_scripts(self) -> list[str]:
        """返回组件所需的 JS 脚本路径列表。

        返回:
            list[str]: 相对于主题 assets 目录的脚本路径，默认为空。
        """
        return []

    def get_required_styles(self) -> list[str]:
        """返回组件所需的 CSS 样式路径列表。

        返回:
            list[str]: 相对于主题 assets 目录的样式路径，默认为空。
        """
        return []

    def get_render_data(self) -> dict[str, Any | Awaitable[Any]]:
        """返回传递给模板的上下文数据。

        排除通用样式字段，模板中通过 data.inline_style 等访问它们。

        返回:
            dict[str, Any | Awaitable[Any]]: 模板渲染上下文数据。
        """
        return model_dump(
            self, exclude={"inline_style", "component_css", "inline_style_str"}
        )

    @compat_computed_field
    def inline_style_str(self) -> str:
        """把内联样式字典序列化为 CSS 字符串。

        返回:
            str: 形如 "k1: v1; k2: v2" 的样式串，为空时返回空字符串。
        """
        if not self.inline_style:
            return ""
        return "; ".join(f"{k}: {v}" for k, v in self.inline_style.items())

    def get_extra_css(self, context: Any) -> str | Awaitable[str]:
        """组件提供的额外 CSS，默认为空。

        参数:
            context: 当前渲染上下文对象。

        返回:
            str | Awaitable[str]: 注入到页面的额外 CSS 字符串或协程。
        """
        return ""


class ContainerComponent(RenderableComponent, ABC):
    """容器类组件基类，封装子组件依赖聚合的通用逻辑。"""

    @abstractmethod
    def get_children(self) -> Iterable[RenderableComponent]:
        """返回全部直接子组件。

        返回:
            Iterable[RenderableComponent]: 直接子组件集合。
        """
        raise NotImplementedError

    def _aggregate_deps(self, attr: str) -> list[str]:
        """聚合自身与所有子组件的指定依赖。

        参数:
            attr: 依赖方法名（get_required_scripts / get_required_styles）。

        返回:
            list[str]: 去重后的依赖路径列表。
        """
        deps = set(getattr(super(), attr)())
        for child in self.get_children():
            if child:
                deps.update(getattr(child, attr)())
        return list(deps)

    def get_required_scripts(self) -> list[str]:
        """聚合子组件所需的脚本。

        返回:
            list[str]: 组件树中全部脚本路径（去重）。
        """
        return self._aggregate_deps("get_required_scripts")

    def get_required_styles(self) -> list[str]:
        """聚合子组件所需的样式。

        返回:
            list[str]: 组件树中全部样式路径（去重）。
        """
        return self._aggregate_deps("get_required_styles")
