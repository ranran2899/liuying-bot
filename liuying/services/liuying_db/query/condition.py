"""条件查询方法模块"""

from collections.abc import Callable
from datetime import datetime
from typing import Any, Self

from sqlalchemy import ColumnElement, and_, not_, or_

from ..utils import DbUtils
from .django_style import DjangoStyleMixin


class ConditionQueryBuilder:
    """条件查询构建器，提供各种条件查询方法"""

    __slots__ = ()

    model_class: type
    args: tuple[Any, ...]

    def _add_condition(
        self,
        column: str | Any,
        condition: ColumnElement[bool],
    ) -> Self:
        """添加查询条件的通用方法

        参数:
            column: 列名或列对象
            condition: 查询条件

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        self.args = (*self.args, condition)
        return self

    def _get_column_condition(
        self,
        column: str | Any,
        condition_fn: Callable[[Any], ColumnElement[bool]],
    ) -> Self:
        """根据列和条件函数添加条件的通用方法

        参数:
            column: 列名或列对象
            condition_fn: 接受列对象并返回条件的函数

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        col = DbUtils.get_column(self.model_class, column)
        return self._add_condition(column, condition_fn(col))

    def where_in(
        self,
        column: str | Any,
        values: list[Any],
    ) -> Self:
        """添加IN条件查询

        参数:
            column: 列名或列对象
            values: 值列表

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        return self._get_column_condition(column, lambda col: col.in_(values))

    def where_not_in(
        self,
        column: str | Any,
        values: list[Any],
    ) -> Self:
        """添加NOT IN条件查询

        参数:
            column: 列名或列对象
            values: 值列表

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        return self._get_column_condition(column, lambda col: col.notin_(values))

    def where_between(
        self,
        column: str | Any,
        start: Any,
        end: Any,
        inclusive: bool = True,
    ) -> Self:
        """添加范围条件查询

        参数:
            column: 列名或列对象
            start: 起始值
            end: 结束值
            inclusive: 是否包含边界，默认True

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        col = DbUtils.get_column(self.model_class, column)
        condition = (
            col.between(start, end) if inclusive else and_(col > start, col < end)
        )
        return self._add_condition(column, condition)

    def where_not_between(
        self,
        column: str | Any,
        start: Any,
        end: Any,
    ) -> Self:
        """添加NOT BETWEEN条件查询
        参数:
            column: 列名或列对象
            start: 起始值
            end: 结束值

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        return self._get_column_condition(
            column, lambda col: not_(col.between(start, end))
        )

    def where_like(
        self,
        column: str | Any,
        pattern: str,
    ) -> Self:
        """添加LIKE条件查询

        参数:
            column: 列名或列对象
            pattern: 匹配模式

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        return self._get_column_condition(column, lambda col: col.like(pattern))

    def where_ilike(
        self,
        column: str | Any,
        pattern: str,
    ) -> Self:
        """添加ILIKE条件查询（PostgreSQL不区分大小写匹配）

        参数:
            column: 列名或列对象
            pattern: 匹配模式

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        return self._get_column_condition(column, lambda col: col.ilike(pattern))

    def where_not_like(
        self,
        column: str | Any,
        pattern: str,
    ) -> Self:
        """添加NOT LIKE条件查询

        参数:
            column: 列名或列对象
            pattern: 匹配模式

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        return self._get_column_condition(column, lambda col: not_(col.like(pattern)))

    def where_not_ilike(
        self,
        column: str | Any,
        pattern: str,
    ) -> Self:
        """添加NOT ILIKE条件查询

        参数:
            column: 列名或列对象
            pattern: 匹配模式

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        return self._get_column_condition(column, lambda col: not_(col.ilike(pattern)))

    def where_startswith(
        self,
        column: str | Any,
        prefix: str,
    ) -> Self:
        """添加前缀匹配条件查询

        参数:
            column: 列名或列对象
            prefix: 前缀字符串

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        return self._get_column_condition(column, lambda col: col.startswith(prefix))

    def where_endswith(
        self,
        column: str | Any,
        suffix: str,
    ) -> Self:
        """添加后缀匹配条件查询

        参数:
            column: 列名或列对象
            suffix: 后缀字符串

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        return self._get_column_condition(column, lambda col: col.endswith(suffix))

    def where_contains(
        self,
        column: str | Any,
        substring: str,
        case_sensitive: bool = True,
    ) -> Self:
        """添加包含匹配条件查询

        参数:
            column: 列名或列对象
            substring: 子字符串
            case_sensitive: 是否区分大小写，默认True

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        col = DbUtils.get_column(self.model_class, column)
        pattern = f"%{DjangoStyleMixin._escape_like(substring)}%"
        if case_sensitive:
            condition = col.like(pattern, escape="\\")
        else:
            condition = col.ilike(pattern, escape="\\")
        return self._add_condition(column, condition)

    def where_null(self, column: str | Any) -> Self:
        """添加IS NULL条件查询

        参数:
            column: 列名或列对象

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        return self._get_column_condition(column, lambda col: col.is_(None))

    def where_not_null(self, column: str | Any) -> Self:
        """添加IS NOT NULL条件查询

        参数:
            column: 列名或列对象

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        return self._get_column_condition(column, lambda col: col.isnot(None))

    def where_gt(
        self,
        column: str | Any,
        value: Any,
    ) -> Self:
        """添加大于条件查询

        参数:
            column: 列名或列对象
            value: 比较值

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        return self._get_column_condition(column, lambda col: col > value)

    def where_gte(
        self,
        column: str | Any,
        value: Any,
    ) -> Self:
        """添加大于等于条件查询

        参数:
            column: 列名或列对象
            value: 比较值

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        return self._get_column_condition(column, lambda col: col >= value)

    def where_lt(
        self,
        column: str | Any,
        value: Any,
    ) -> Self:
        """添加小于条件查询

        参数:
            column: 列名或列对象
            value: 比较值

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        return self._get_column_condition(column, lambda col: col < value)

    def where_lte(
        self,
        column: str | Any,
        value: Any,
    ) -> Self:
        """添加小于等于条件查询

        参数:
            column: 列名或列对象
            value: 比较值

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        return self._get_column_condition(column, lambda col: col <= value)

    def where_eq(
        self,
        column: str | Any,
        value: Any,
    ) -> Self:
        """添加等于条件查询

        参数:
            column: 列名或列对象
            value: 比较值

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        return self._get_column_condition(column, lambda col: col == value)

    def where_ne(
        self,
        column: str | Any,
        value: Any,
    ) -> Self:
        """添加不等于条件查询

        参数:
            column: 列名或列对象
            value: 比较值

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        return self._get_column_condition(column, lambda col: col != value)

    def where_or(
        self,
        *conditions: tuple[str | Any, str, Any],
    ) -> Self:
        """添加OR多条件组合查询

        参数:
            *conditions: 条件元组列表，每个元组格式为 (列名, 操作符, 值)
                         操作符支持: 'eq', 'ne', 'gt', 'gte', 'lt', 'lte',
                         'like', 'ilike', 'in', 'not_in', 'is_null', 'is_not_null'

        返回:
            QueryWrapper: 返回自身以支持链式调用

        示例:
            Model.filter().where_or(
                ("name", "like", "%test%"),
                ("status", "eq", 1),
            )
        """
        clauses = []
        for col, op, val in conditions:
            column = DbUtils.get_column(self.model_class, col)
            match op:
                case "eq":
                    clauses.append(column == val)
                case "ne":
                    clauses.append(column != val)
                case "gt":
                    clauses.append(column > val)
                case "gte":
                    clauses.append(column >= val)
                case "lt":
                    clauses.append(column < val)
                case "lte":
                    clauses.append(column <= val)
                case "like":
                    clauses.append(column.like(val))
                case "ilike":
                    clauses.append(column.ilike(val))
                case "in":
                    clauses.append(column.in_(val))
                case "not_in":
                    clauses.append(column.notin_(val))
                case "is_null":
                    clauses.append(column.is_(None))
                case "is_not_null":
                    clauses.append(column.isnot(None))
                case _:
                    raise ValueError(f"不支持的操作符: {op}")

        if clauses:
            self.args = (*self.args, or_(*clauses))
        return self

    def _where_date_period(
        self,
        column: str | Any,
        period: str,
    ) -> Self:
        """添加日期范围查询的通用方法

        参数:
            column: 列名或列对象
            period: 时间周期

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        col = DbUtils.get_column(self.model_class, column)
        start, end = DbUtils.get_date_range(period)
        return self._add_condition(column, and_(col >= start, col <= end))

    def where_today(self, column: str | Any) -> Self:
        """查询今天的记录

        参数:
            column: 列名或列对象

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        return self._where_date_period(column, "today")

    def where_yesterday(self, column: str | Any) -> Self:
        """查询昨天的记录

        参数:
            column: 列名或列对象

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        return self._where_date_period(column, "yesterday")

    def where_this_week(self, column: str | Any) -> Self:
        """查询本周的记录

        参数:
            column: 列名或列对象

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        return self._where_date_period(column, "this_week")

    def where_last_week(self, column: str | Any) -> Self:
        """查询上周的记录

        参数:
            column: 列名或列对象

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        return self._where_date_period(column, "last_week")

    def where_this_month(self, column: str | Any) -> Self:
        """查询本月的记录

        参数:
            column: 列名或列对象

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        return self._where_date_period(column, "this_month")

    def where_last_month(self, column: str | Any) -> Self:
        """查询上月的记录

        参数:
            column: 列名或列对象

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        return self._where_date_period(column, "last_month")

    def where_this_year(self, column: str | Any) -> Self:
        """查询本年的记录

        参数:
            column: 列名或列对象

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        return self._where_date_period(column, "this_year")

    def where_last_year(self, column: str | Any) -> Self:
        """查询上年的记录

        参数:
            column: 列名或列对象

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        return self._where_date_period(column, "last_year")

    def where_in_date_range(
        self,
        column: str | Any,
        start_date: datetime,
        end_date: datetime,
    ) -> Self:
        """查询指定日期范围内的记录

        参数:
            column: 列名或列对象
            start_date: 开始日期
            end_date: 结束日期

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        col = DbUtils.get_column(self.model_class, column)
        return self._add_condition(column, and_(col >= start_date, col <= end_date))
