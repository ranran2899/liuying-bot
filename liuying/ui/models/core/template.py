"""独立模板文件组件数据模型。"""

from pathlib import Path
from typing import Any

from pydantic import Field

from .base import RenderableComponent

__all__ = ["TemplateComponent"]


class TemplateComponent(RenderableComponent):
    """基于独立模板文件的 UI 组件。"""

    _is_standalone_template: bool = True
    """标记此组件为独立模板"""
    template_path: str | Path = Field(..., description="指向 HTML 模板文件的路径")
    """指向 HTML 模板文件的路径"""
    data: dict[str, Any] = Field(..., description="传递给模板的上下文数据字典")
    """传递给模板的上下文数据字典"""

    @property
    def template_name(self) -> str:
        """返回模板路径字符串。

        返回:
            str: 模板路径（Path 转为 POSIX 风格字符串）。
        """
        if isinstance(self.template_path, Path):
            return self.template_path.as_posix()
        return str(self.template_path)

    def get_render_data(self) -> dict[str, Any]:
        """返回传递给模板的数据。

        返回:
            dict[str, Any]: 初始化时传入的上下文数据字典。
        """
        return self.data

    def __getattr__(self, name: str) -> Any:
        """允许直接访问 data 字典中的键。

        参数:
            name: 属性名，等价于 data 中的键名。

        返回:
            Any: data[name] 的值。

        异常:
            AttributeError: data 中不存在该键时抛出。
        """
        try:
            return self.data[name]
        except KeyError:
            raise AttributeError(
                f"'{type(self).__name__}' 对象没有属性 '{name}'"
            ) from None
