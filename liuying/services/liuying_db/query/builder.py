"""查询构建器 Mixin

提供链式调用的查询构建方法，包括过滤、排序、分页、分组、
锁、缓存、关联加载以及完整的 where_* 条件查询方法族。

由 ``QueryWrapper`` 组合使用，不单独实例化。
"""

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import ColumnElement, and_, func, not_, or_

from ..utils import DbUtils
from .conditions import _COMPARISON_OPS, _escape_like

if TYPE_CHECKING:
    from ..base_model import Model
    from . import QueryWrapper


class QueryBuilderMixin[T: Model]:
    """查询构建方法集合

    提供链式查询构建能力和 where_* 条件查询方法族。
    所有方法返回自身以支持链式调用。
    """

    # ========== 查询构建方法 ==========

    def filter(
        self, *args: Any, skip_none: bool = False, **kwargs: Any
    ) -> "QueryWrapper[T]":
        """添加过滤条件

        参数:
            *args: 过滤条件，支持 SQLAlchemy 表达式或 Q 对象
            skip_none: 为True时忽略值为None的kwargs条件
            **kwargs: 过滤条件，支持 Django 风格双下划线语法。
                      重复键以最后一次调用的值为准（覆盖语义），
                      args 表达式始终叠加。

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        self.args = self.args + args
        if skip_none:
            kwargs = {k: v for k, v in kwargs.items() if v is not None}
        # 后调用覆盖前值，避免 model.filter(a=1).filter(a=2) 生成永假条件
        self.kwargs = {**self.kwargs, **kwargs}
        return self

    def exclude(self, *args: Any, **kwargs: Any) -> "QueryWrapper[T]":
        """添加排除条件，生成 NOT(...) 条件

        参数:
            *args: SQLAlchemy 条件表达式或 Q 对象
            **kwargs: Django 风格或普通等值查询条件

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        self._exclude_args = self._exclude_args + args
        self._exclude_kwargs.update(kwargs)
        return self

    def limit(self, limit: int) -> "QueryWrapper[T]":
        """设置查询结果数量限制

        参数:
            limit: 限制数量

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        self._limit = limit
        return self

    def offset(self, offset: int) -> "QueryWrapper[T]":
        """设置查询结果偏移量

        参数:
            offset: 偏移量

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        self._offset = offset
        return self

    def order_by(self, *order_by: str | Any) -> "QueryWrapper[T]":
        """设置排序条件

        支持格式: "-字段名"降序, "字段名"升序, "字段名 DESC/ASC", 列对象

        参数:
            *order_by: 排序条件

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        self._order_by = tuple(self._process_order_item(item) for item in order_by)
        return self

    def in_random_order(self) -> "QueryWrapper[T]":
        """随机排序查询结果

        注意: 使用 SQL ``random()`` 函数，MySQL 方言为 ``rand()``，
        跨数据库使用时需注意兼容性。

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        self._order_by = (func.random(),)
        return self

    def distinct(self) -> "QueryWrapper[T]":
        """设置去重查询结果

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        self._distinct = True
        return self

    def join(self, target: Any, onclause: Any = None) -> "QueryWrapper[T]":
        """添加表连接条件

        参数:
            target: 要连接的表
            onclause: 连接条件

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        self._join_conditions.append({"target": target, "onclause": onclause})
        return self

    def group_by(self, *criterion: Any) -> "QueryWrapper[T]":
        """设置分组条件

        参数:
            *criterion: 分组条件

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        self._group_by = criterion
        return self

    def having(self, criterion: Any) -> "QueryWrapper[T]":
        """设置分组后的过滤条件

        参数:
            criterion: 过滤条件

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        self._having = criterion
        return self

    def values(self, *columns: str | Any) -> "QueryWrapper[T]":
        """指定查询字段

        参数:
            *columns: 要查询的字段

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        self._values = columns
        return self

    def annotate(self, **annotations: ColumnElement[Any]) -> "QueryWrapper[T]":
        """添加聚合标注

        参数:
            **annotations: 标注名称与聚合表达式

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        self._annotations = annotations
        return self

    def defer(self, *fields: str | Any) -> "QueryWrapper[T]":
        """延迟加载指定字段

        参数:
            *fields: 要延迟加载的字段名或列属性

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        self._deferred_fields = [
            DbUtils.get_column(self.model_class, f) if isinstance(f, str) else f
            for f in fields
        ]
        return self

    def only(self, *fields: str) -> "QueryWrapper[T]":
        """只查询指定字段

        参数:
            *fields: 要查询的字段

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        self._values = tuple(DbUtils.get_column(self.model_class, f) for f in fields)
        return self

    def except_(self, *fields: str) -> "QueryWrapper[T]":
        """排除指定字段查询

        参数:
            *fields: 要排除的字段名

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        self._values = tuple(
            col for col in self.model_class.__table__.columns if col.name not in fields
        )
        return self

    def select_for_update(
        self,
        nowait: bool = False,
        skip_locked: bool = False,
        read: bool = False,
        key_share: bool = False,
    ) -> "QueryWrapper[T]":
        """添加 SELECT FOR UPDATE 行锁

        参数:
            nowait: 是否使用 NOWAIT
            skip_locked: 是否跳过已锁定行
            read: 是否使用 FOR SHARE 模式
            key_share: 是否使用 KEY SHARE 模式

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        self._for_update_options = {
            "nowait": nowait,
            "skip_locked": skip_locked,
            "read": read,
            "key_share": key_share,
        }
        return self

    def using(self, db_name: str) -> "QueryWrapper[T]":
        """指定要使用的数据库名称

        参数:
            db_name: 数据库名称

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        self._db_name = db_name
        return self

    def with_deleted(self) -> "QueryWrapper[T]":
        """包含已删除的记录（软删除支持）

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        self._with_deleted = True
        return self

    def only_deleted(self) -> "QueryWrapper[T]":
        """只查询已删除的记录（软删除支持）

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        self._with_deleted = True
        if hasattr(self.model_class, "deleted_at"):
            self.args = (
                *self.args,
                getattr(self.model_class, "deleted_at").isnot(None),
            )
        return self

    def cache(self, key: str | None = None, ttl: int = 300) -> "QueryWrapper[T]":
        """设置查询结果缓存

        仅对返回模型实体的查询生效（``first``/``all``/``one``/``one_or_none``），
        返回行或标量的方法（``values``/``aggregate``/``count``/``exists`` 等）
        不会应用缓存。缓存命中时返回反序列化重建的脱离会话实例，
        不支持懒加载关系属性。

        参数:
            key: 缓存键，默认为None自动生成
            ttl: 缓存过期时间（秒），默认为300秒

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        self._cache_key = key
        self._cache_ttl = ttl
        return self

    def select_related(self, *relationships) -> "QueryWrapper[T]":
        """使用 joinedload 策略预加载（适合一对一关系）

        参数:
            *relationships: 要预加载的关系名称

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        for rel in relationships:
            self._load_relationships.append((rel, {"strategy": "joined"}))
        return self

    def prefetch_related(self, *relationships) -> "QueryWrapper[T]":
        """使用 selectinload 策略预加载（适合一对多关系）

        参数:
            *relationships: 要预加载的关系名称

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        for rel in relationships:
            self._load_relationships.append((rel, {"strategy": "selectin"}))
        return self

    # ========== 条件查询方法 ==========

    def _add_condition(self, condition: ColumnElement[bool]) -> "QueryWrapper[T]":
        """添加查询条件的通用方法

        参数:
            condition: 查询条件

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        self.args = (*self.args, condition)
        return self

    def _col_cond(
        self, column: str | Any, fn: Callable[[Any], ColumnElement[bool]]
    ) -> "QueryWrapper[T]":
        """根据列和条件函数添加条件

        参数:
            column: 列名或列对象
            fn: 接受列对象并返回条件的函数

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        return self._add_condition(fn(DbUtils.get_column(self.model_class, column)))

    def where_in(self, column: str | Any, values: list[Any]) -> "QueryWrapper[T]":
        """添加 IN 条件查询"""
        return self._col_cond(column, lambda c: c.in_(values))

    def where_not_in(self, column: str | Any, values: list[Any]) -> "QueryWrapper[T]":
        """添加 NOT IN 条件查询"""
        return self._col_cond(column, lambda c: c.notin_(values))

    def where_between(
        self, column: str | Any, start: Any, end: Any, inclusive: bool = True
    ) -> "QueryWrapper[T]":
        """添加范围条件查询

        参数:
            column: 列名或列对象
            start: 起始值
            end: 结束值
            inclusive: 是否包含边界，默认True
        """
        col = DbUtils.get_column(self.model_class, column)
        cond = col.between(start, end) if inclusive else and_(col > start, col < end)
        return self._add_condition(cond)

    def where_not_between(
        self, column: str | Any, start: Any, end: Any
    ) -> "QueryWrapper[T]":
        """添加 NOT BETWEEN 条件查询"""
        return self._col_cond(column, lambda c: not_(c.between(start, end)))

    def where_like(self, column: str | Any, pattern: str) -> "QueryWrapper[T]":
        """添加 LIKE 条件查询"""
        return self._col_cond(column, lambda c: c.like(pattern))

    def where_ilike(self, column: str | Any, pattern: str) -> "QueryWrapper[T]":
        """添加 ILIKE 条件查询（不区分大小写匹配）"""
        return self._col_cond(column, lambda c: c.ilike(pattern))

    def where_not_like(self, column: str | Any, pattern: str) -> "QueryWrapper[T]":
        """添加 NOT LIKE 条件查询"""
        return self._col_cond(column, lambda c: not_(c.like(pattern)))

    def where_not_ilike(self, column: str | Any, pattern: str) -> "QueryWrapper[T]":
        """添加 NOT ILIKE 条件查询"""
        return self._col_cond(column, lambda c: not_(c.ilike(pattern)))

    def where_startswith(self, column: str | Any, prefix: str) -> "QueryWrapper[T]":
        """添加前缀匹配条件查询"""
        return self._col_cond(column, lambda c: c.startswith(prefix))

    def where_endswith(self, column: str | Any, suffix: str) -> "QueryWrapper[T]":
        """添加后缀匹配条件查询"""
        return self._col_cond(column, lambda c: c.endswith(suffix))

    def where_contains(
        self, column: str | Any, substring: str, case_sensitive: bool = True
    ) -> "QueryWrapper[T]":
        """添加包含匹配条件查询

        参数:
            column: 列名或列对象
            substring: 子字符串
            case_sensitive: 是否区分大小写，默认True
        """
        col = DbUtils.get_column(self.model_class, column)
        pattern = f"%{_escape_like(substring)}%"
        cond = (
            col.like(pattern, escape="\\")
            if case_sensitive
            else col.ilike(pattern, escape="\\")
        )
        return self._add_condition(cond)

    def where_null(self, column: str | Any) -> "QueryWrapper[T]":
        """添加 IS NULL 条件查询"""
        return self._col_cond(column, lambda c: c.is_(None))

    def where_not_null(self, column: str | Any) -> "QueryWrapper[T]":
        """添加 IS NOT NULL 条件查询"""
        return self._col_cond(column, lambda c: c.isnot(None))

    def where_gt(self, column: str | Any, value: Any) -> "QueryWrapper[T]":
        """添加大于条件查询"""
        return self._col_cond(column, lambda c: c > value)

    def where_gte(self, column: str | Any, value: Any) -> "QueryWrapper[T]":
        """添加大于等于条件查询"""
        return self._col_cond(column, lambda c: c >= value)

    def where_lt(self, column: str | Any, value: Any) -> "QueryWrapper[T]":
        """添加小于条件查询"""
        return self._col_cond(column, lambda c: c < value)

    def where_lte(self, column: str | Any, value: Any) -> "QueryWrapper[T]":
        """添加小于等于条件查询"""
        return self._col_cond(column, lambda c: c <= value)

    def where_eq(self, column: str | Any, value: Any) -> "QueryWrapper[T]":
        """添加等于条件查询"""
        return self._col_cond(column, lambda c: c == value)

    def where_ne(self, column: str | Any, value: Any) -> "QueryWrapper[T]":
        """添加不等于条件查询"""
        return self._col_cond(column, lambda c: c != value)

    def where_or(self, *conditions: tuple[str | Any, str, Any]) -> "QueryWrapper[T]":
        """添加 OR 多条件组合查询

        参数:
            *conditions: 条件元组列表，每个元组格式为 (列名, 操作符, 值)
                         操作符支持: eq/ne/gt/gte/lt/lte/like/ilike/contains/
                                    icontains/startswith/endswith/in/not_in/
                                    is_null/is_not_null/between/regex

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        clauses: list[ColumnElement[bool]] = []
        for col, op, val in conditions:
            builder = _COMPARISON_OPS.get(op)
            if builder is None:
                raise ValueError(f"不支持的操作符: {op}")
            clauses.append(builder(DbUtils.get_column(self.model_class, col), val))
        if clauses:
            self.args = (*self.args, or_(*clauses))
        return self

    def _where_date_period(self, column: str | Any, period: str) -> "QueryWrapper[T]":
        """添加日期范围查询的通用方法"""
        col = DbUtils.get_column(self.model_class, column)
        start, end = DbUtils.get_date_range(period)
        return self._add_condition(and_(col >= start, col <= end))

    def where_today(self, column: str | Any) -> "QueryWrapper[T]":
        """查询今天的记录"""
        return self._where_date_period(column, "today")

    def where_yesterday(self, column: str | Any) -> "QueryWrapper[T]":
        """查询昨天的记录"""
        return self._where_date_period(column, "yesterday")

    def where_this_week(self, column: str | Any) -> "QueryWrapper[T]":
        """查询本周的记录"""
        return self._where_date_period(column, "this_week")

    def where_last_week(self, column: str | Any) -> "QueryWrapper[T]":
        """查询上周的记录"""
        return self._where_date_period(column, "last_week")

    def where_this_month(self, column: str | Any) -> "QueryWrapper[T]":
        """查询本月的记录"""
        return self._where_date_period(column, "this_month")

    def where_last_month(self, column: str | Any) -> "QueryWrapper[T]":
        """查询上月的记录"""
        return self._where_date_period(column, "last_month")

    def where_this_year(self, column: str | Any) -> "QueryWrapper[T]":
        """查询本年的记录"""
        return self._where_date_period(column, "this_year")

    def where_last_year(self, column: str | Any) -> "QueryWrapper[T]":
        """查询上年的记录"""
        return self._where_date_period(column, "last_year")

    def where_in_date_range(
        self, column: str | Any, start_date: datetime, end_date: datetime
    ) -> "QueryWrapper[T]":
        """查询指定日期范围内的记录"""
        col = DbUtils.get_column(self.model_class, column)
        return self._add_condition(and_(col >= start_date, col <= end_date))

    # ========== 查询构建内部方法 ==========

    def _process_order_item(self, item: str | Any) -> Any:
        """处理单个排序项

        参数:
            item: 排序项（字符串或列对象）

        返回:
            排序后的列对象
        """
        if not isinstance(item, str):
            return item
        match item:
            case s if s.startswith("-"):
                return DbUtils.get_column(self.model_class, s[1:]).desc()
            case s if s.upper().endswith(" DESC"):
                field = s.rsplit(maxsplit=1)[0]
                return DbUtils.get_column(self.model_class, field).desc()
            case s if s.upper().endswith(" ASC"):
                field = s.rsplit(maxsplit=1)[0]
                return DbUtils.get_column(self.model_class, field).asc()
            case s:
                return DbUtils.get_column(self.model_class, s)
