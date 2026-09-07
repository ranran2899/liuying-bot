"""链式构建通用表格的辅助类。"""

from pathlib import Path
from typing import Any, Literal, Self

from ...models.core.table import (
    BaseCell,
    ImageCell,
    TableCell,
    TableData,
    TextCell,
)
from ..base import BaseBuilder

__all__ = ["TableBuilder"]


class TableBuilder(BaseBuilder[TableData]):
    """链式构建通用表格的辅助类。"""

    def __init__(self, title: str, tip: str | None = None):
        """初始化表格构建器。

        参数:
            title: 表格主标题。
            tip: 表格下方的可选提示信息，反引号包裹的片段会渲染为行内代码。
        """
        data_model = TableData(title=title, tip=tip, headers=[], rows=[])
        super().__init__(data_model, template_name="components/core/table")

    def _normalize_cell(self, cell_data: Any) -> TableCell:
        """把各种原生数据类型转换为 TableCell 模型。

        参数:
            cell_data: 单元格数据，支持 BaseCell / str / int / float /
                Path（图片）/ (Path, 宽, 高) 元组。

        返回:
            TableCell: 转换后的单元格模型，无法识别时返回空文本单元格。
        """
        match cell_data:
            case BaseCell():
                return cell_data
            case str() | int() | float():
                return TextCell(content=str(cell_data))
            case Path():
                return ImageCell(src=cell_data.resolve().as_uri())
            case (p, w, h) if (
                isinstance(p, Path)
                and isinstance(w, int)
                and isinstance(h, int)
            ):
                return ImageCell(src=p.resolve().as_uri(), width=w, height=h)
            case _:
                return TextCell(content="")

    def set_headers(self, headers: list[str]) -> Self:
        """设置表格的表头。

        参数:
            headers: 表头文本列表。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.headers = headers
        return self

    def set_column_alignments(
        self, alignments: list[Literal["left", "center", "right"]]
    ) -> Self:
        """设置表格每列的文本对齐方式。

        参数:
            alignments: 每列的对齐方式列表。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.column_alignments = alignments
        return self

    def set_column_widths(self, widths: list[str | int]) -> Self:
        """设置每列的宽度。

        参数:
            widths: 每列宽度列表，CSS 值字符串或像素整数（如 ['50px', 100]）。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.column_widths = widths
        return self

    def add_row(self, row: list[TableCell]) -> Self:
        """向表格中添加一行数据。

        参数:
            row: 单元格列表，原生类型会自动转换为对应模型。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.rows.append([self._normalize_cell(cell) for cell in row])
        return self

    def add_rows(self, rows: list[list[TableCell]]) -> Self:
        """向表格中批量添加多行数据。

        参数:
            rows: 多行单元格列表。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        for row in rows:
            self.add_row(row)
        return self
