"""链式构建 Notebook 页面的辅助类。"""

from ...models.core.base import RenderableComponent
from ...models.core.notebook import NotebookData, NotebookElement
from ...models.widgets.divider import Divider
from ..base import BaseBuilder, resolve_image_src, to_component

__all__ = ["NotebookBuilder"]


class NotebookBuilder(BaseBuilder[NotebookData]):
    """链式构建 Notebook 页面的辅助类。"""

    def __init__(self, data: list[NotebookElement] | None = None):
        """初始化 Notebook 构建器。

        参数:
            data: 初始元素列表，为 None 时从空页面开始。
        """
        elements = data if data is not None else []
        data_model = NotebookData(elements=elements)
        super().__init__(data_model, template_name="components/core/notebook")
        self._elements = elements

    def text(self, text: str) -> "NotebookBuilder":
        """添加文本段落。

        参数:
            text: 段落文本，支持 Markdown 内联语法。

        返回:
            NotebookBuilder: 构建器自身，支持链式调用。
        """
        self._elements.append(NotebookElement(type="paragraph", text=text))
        return self

    def head(self, text: str, level: int = 1) -> "NotebookBuilder":
        """添加标题。

        参数:
            text: 标题文本。
            level: 标题级别，1-4。

        返回:
            NotebookBuilder: 构建器自身，支持链式调用。

        异常:
            ValueError: 标题级别不在 1-4 范围内时抛出。
        """
        if not 1 <= level <= 4:
            raise ValueError("标题级别必须在1-4之间")
        self._elements.append(
            NotebookElement(type="heading", text=text, level=level)
        )
        return self

    def image(
        self, content: str, caption: str | None = None
    ) -> "NotebookBuilder":
        """添加图片。

        参数:
            content: 图片来源，支持文件路径与 `base64://` 前缀的数据。
            caption: 图片的说明文字。

        返回:
            NotebookBuilder: 构建器自身，支持链式调用。
        """
        self._elements.append(
            NotebookElement(
                type="image", src=resolve_image_src(content), caption=caption
            )
        )
        return self

    def quote(self, text: str | list[str]) -> "NotebookBuilder":
        """添加引用文本，支持批量。

        参数:
            text: 单条引用文本，或引用文本列表。

        返回:
            NotebookBuilder: 构建器自身，支持链式调用。
        """
        for t in ([text] if isinstance(text, str) else text):
            self._elements.append(NotebookElement(type="blockquote", text=t))
        return self

    def code(self, code: str, language: str = "python") -> "NotebookBuilder":
        """添加代码块。

        参数:
            code: 代码内容。
            language: 代码语言标注。

        返回:
            NotebookBuilder: 构建器自身，支持链式调用。
        """
        self._elements.append(
            NotebookElement(type="code", code=code, language=language)
        )
        return self

    def add_list(
        self, items: list[str], ordered: bool = False
    ) -> "NotebookBuilder":
        """添加列表。

        参数:
            items: 列表项文本列表。
            ordered: 是否为有序列表。

        返回:
            NotebookBuilder: 构建器自身，支持链式调用。
        """
        self._elements.append(
            NotebookElement(type="list", data=items, ordered=ordered)
        )
        return self

    def add_divider(self, **kwargs) -> "NotebookBuilder":
        """添加分隔线组件。

        参数:
            **kwargs: 传递给 Divider 组件的可选参数（如 margin/color）。

        返回:
            NotebookBuilder: 构建器自身，支持链式调用。
        """
        return self.add_component(Divider(**kwargs))

    def add_component(
        self, component: "RenderableComponent | BaseBuilder"
    ) -> "NotebookBuilder":
        """添加一个可渲染的自定义组件。

        参数:
            component: 组件模型或构建器。

        返回:
            NotebookBuilder: 构建器自身，支持链式调用。
        """
        self._elements.append(
            NotebookElement(type="component", component=to_component(component))
        )
        return self

    def add_texts(self, texts: list[str]) -> "NotebookBuilder":
        """批量添加多个文本段落。

        参数:
            texts: 段落文本列表。

        返回:
            NotebookBuilder: 构建器自身，支持链式调用。
        """
        for text_item in texts:
            self.text(text_item)
        return self

    def add_quotes(self, quotes: list[str]) -> "NotebookBuilder":
        """批量添加引用。

        参数:
            quotes: 引用文本列表。

        返回:
            NotebookBuilder: 构建器自身，支持链式调用。
        """
        for q in quotes:
            self.quote(q)
        return self

    def build(self) -> NotebookData:
        """构建并返回 NotebookData 模型实例。

        返回:
            NotebookData: 配置完成的数据模型实例。
        """
        self._data.elements = self._elements
        return super().build()
