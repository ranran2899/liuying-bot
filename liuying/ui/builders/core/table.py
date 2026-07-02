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
        data_model = TableData(title=title, tip=tip, headers=[], rows=[])
        super().__init__(data_model, template_name="components/core/table")

    def _normalize_cell(self, cell_data: Any) -> TableCell:
        """将各种原生数据类型转换为TableCell模型。"""
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
        """设置表格的表头。"""
        self._data.headers = headers
        return self

    def set_column_alignments(
        self, alignments: list[Literal["left", "center", "right"]]
    ) -> Self:
        """设置表格每列的文本对齐方式。"""
        self._data.column_alignments = alignments
        return self

    def set_column_widths(self, widths: list[str | int]) -> Self:
        """设置每列的宽度。"""
        self._data.column_widths = widths
        return self

    def add_row(self, row: list[TableCell]) -> Self:
        """向表格中添加一行数据。"""
        self._data.rows.append(
            [self._normalize_cell(cell) for cell in row]
        )
        return self

    def add_rows(self, rows: list[list[TableCell]]) -> Self:
        """向表格中批量添加多行数据。"""
        for row in rows:
            self.add_row(row)
        return self
