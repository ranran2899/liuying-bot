from pathlib import Path

from ...models.components import Divider
from ...models.core.base import RenderableComponent
from ...models.core.notebook import NotebookData, NotebookElement
from ..base import BaseBuilder

__all__ = ["NotebookBuilder"]


def _resolve_image_src(content: str | Path) -> str:
    """解析图片内容为可用的src路径。"""
    if isinstance(content, Path):
        return content.absolute().as_uri()
    if content.startswith("base64://"):
        return f"data:image/png;base64,{content.removeprefix('base64://')}"
    return content


class NotebookBuilder(BaseBuilder[NotebookData]):
    """链式构建 Notebook 页面的辅助类。"""

    def __init__(self, data: list[NotebookElement] | None = None):
        elements = data if data is not None else []
        data_model = NotebookData(elements=elements)
        super().__init__(data_model, template_name="components/core/notebook")
        self._elements = elements

    def text(self, text: str) -> "NotebookBuilder":
        """添加文本段落。"""
        self._elements.append(NotebookElement(type="paragraph", text=text))
        return self

    def head(self, text: str, level: int = 1) -> "NotebookBuilder":
        """添加标题。"""
        if not 1 <= level <= 4:
            raise ValueError("标题级别必须在1-4之间")
        self._elements.append(
            NotebookElement(type="heading", text=text, level=level)
        )
        return self

    def image(
        self, content: str, caption: str | None = None,
    ) -> "NotebookBuilder":
        """添加图片。"""
        self._elements.append(
            NotebookElement(
                type="image", src=_resolve_image_src(content), caption=caption
            )
        )
        return self

    def quote(self, text: str | list[str]) -> "NotebookBuilder":
        """添加引用文本。"""
        texts = [text] if isinstance(text, str) else text
        for t in texts:
            self._elements.append(NotebookElement(type="blockquote", text=t))
        return self

    def code(self, code: str, language: str = "python") -> "NotebookBuilder":
        """添加代码块。"""
        self._elements.append(
            NotebookElement(type="code", code=code, language=language)
        )
        return self

    def add_list(
        self, items: list[str], ordered: bool = False
    ) -> "NotebookBuilder":
        """添加列表。"""
        self._elements.append(
            NotebookElement(type="list", data=items, ordered=ordered)
        )
        return self

    def add_divider(self, **kwargs) -> "NotebookBuilder":
        """添加分隔线。"""
        self.add_component(Divider(**kwargs))
        return self

    def add_component(
        self, component: "RenderableComponent | BaseBuilder"
    ) -> "NotebookBuilder":
        """添加一个可渲染的自定义组件。"""
        component_data = (
            component.build() if isinstance(component, BaseBuilder) else component
        )
        if not isinstance(component_data, RenderableComponent):
            raise TypeError(
                f"add_component 只能接受 RenderableComponent 或其 Builder，"
                f"但收到了 {type(component_data)}"
            )
        self._elements.append(
            NotebookElement(type="component", component=component_data)
        )
        return self

    def add_texts(self, texts: list[str]) -> "NotebookBuilder":
        """批量添加多个文本段落。"""
        for text_item in texts:
            self.text(text_item)
        return self

    def add_quotes(self, quotes: list[str]) -> "NotebookBuilder":
        """批量添加引用。"""
        for q in quotes:
            self.quote(q)
        return self

    def build(self) -> NotebookData:
        """构建并返回 NotebookData 模型实例。"""
        self._data.elements = self._elements
        return super().build()
