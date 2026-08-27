"""查询条件构建模块

提供 Django 风格的双下划线查询语法解析、Q 对象条件组合以及
过滤语句构建能力。

核心导出:
    - ``Q``: Django 风格查询条件组合对象，支持 AND/OR/NOT
    - ``build_filter_statement``: 构建 SQLAlchemy 过滤查询语句
    - ``_build_django_conditions``: 构建 Django 风格条件列表
    - ``_separate_kwargs``: 分离普通 kwargs 与 Django 风格 kwargs
    - ``_is_retryable_error``: 判断错误是否可重试
"""

from collections.abc import Callable
from functools import lru_cache
from typing import TYPE_CHECKING, Any, TypeVar

from sqlalchemy import (
    ColumnElement,
    Date,
    Time,
    and_,
    cast,
    func,
    not_,
    or_,
    select,
)
from sqlalchemy.exc import (
    DBAPIError,
    DisconnectionError,
    InterfaceError,
    OperationalError,
)
from sqlalchemy.sql.selectable import Select

from liuying.services.cache import Cache

from ..config import RETRY_CONFIG

if TYPE_CHECKING:
    from ..base_model import Model

T = TypeVar("T", bound="Model")

_MAX_RETRIES = RETRY_CONFIG.max_retries
_BASE_DELAY = RETRY_CONFIG.base_delay
_QUERY_CACHE = Cache("LIUYING_DB_QUERY", result_type=object)


def query_cache_namespace(model_class: type) -> str:
    """构建查询缓存命名空间，按模型隔离缓存失效范围

    参数:
        model_class: 模型类

    返回:
        str: 缓存命名空间
    """
    return f"dbq_{model_class.__name__}"

_RETRYABLE_ERRORS = (OperationalError, DisconnectionError, InterfaceError, DBAPIError)
_NON_RETRYABLE_KEYWORDS = (
    "syntax error",
    "constraint",
    "unique",
    "foreign key",
    "primary key",
    "duplicate",
    "not null",
    "check constraint",
    "no such table",
    "no such column",
)

_RESULT_HANDLERS: dict[str, Callable[[Any], Any]] = {
    "first": lambda r: r.scalars().first(),
    "all": lambda r: r.scalars().all(),
    "one": lambda r: r.scalars().one(),
    "one_or_none": lambda r: r.scalars().one_or_none(),
    "one_row": lambda r: r.one(),
    "one_row_or_none": lambda r: r.one_or_none(),
    "scalar": lambda r: r.scalar(),
    "count": lambda r: r.scalar(),
    "rowcount": lambda r: r.rowcount,
    "first_row": lambda r: r.first(),
    "fetchall": lambda r: r.fetchall(),
    "mapping": lambda r: r.mappings().first(),
    "mappings": lambda r: r.mappings().all(),
}

# Django 风格 lookup 构建器映射
_LOOKUPS: dict[str, Callable[[Any, Any], Any]] = {
    "exact": lambda c, v: c == v,
    "iexact": lambda c, v: c.ilike(_escape_like(str(v)), escape="\\"),
    "contains": lambda c, v: c.like(f"%{_escape_like(str(v))}%", escape="\\"),
    "icontains": lambda c, v: c.ilike(f"%{_escape_like(str(v))}%", escape="\\"),
    "startswith": lambda c, v: c.like(f"{_escape_like(str(v))}%", escape="\\"),
    "istartswith": lambda c, v: c.ilike(f"{_escape_like(str(v))}%", escape="\\"),
    "endswith": lambda c, v: c.like(f"%{_escape_like(str(v))}", escape="\\"),
    "iendswith": lambda c, v: c.ilike(f"%{_escape_like(str(v))}", escape="\\"),
    "gt": lambda c, v: c > v,
    "gte": lambda c, v: c >= v,
    "lt": lambda c, v: c < v,
    "lte": lambda c, v: c <= v,
    "ne": lambda c, v: c != v,
    "in": lambda c, v: c.in_(v),
    "not_in": lambda c, v: c.notin_(v),
    "range": lambda c, v: and_(c >= v[0], c <= v[1]),
    "between": lambda c, v: c.between(v[0], v[1]),
    "isnull": lambda c, v: c.is_(None) if v else c.isnot(None),
    "regex": lambda c, v: c.regexp_match(v),
    "iregex": lambda c, v: c.regexp_match(v, flags="i"),
    "year": lambda c, v: func.extract("year", c) == v,
    "month": lambda c, v: func.extract("month", c) == v,
    "day": lambda c, v: func.extract("day", c) == v,
    "quarter": lambda c, v: func.extract("quarter", c) == v,
    "week": lambda c, v: func.extract("week", c) == v,
    "hour": lambda c, v: func.extract("hour", c) == v,
    "minute": lambda c, v: func.extract("minute", c) == v,
    "second": lambda c, v: func.extract("second", c) == v,
    "week_day": lambda c, v: func.extract("dow", c) == v,
    "date": lambda c, v: cast(c, Date) == v,
    "time": lambda c, v: cast(c, Time) == v,
    "search": lambda c, v: c.match(v),
}


def _escape_like(value: str) -> str:
    """转义 LIKE 查询中的特殊字符

    参数:
        value: 原始字符串

    返回:
        str: 转义后的字符串
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# 短操作符映射，供 where_or 等条件方法复用；
# 与 _LOOKUPS 语义等价的条目直接引用，避免重复定义 lambda
_COMPARISON_OPS: dict[str, Callable[[Any, Any], ColumnElement[bool]]] = {
    "eq": _LOOKUPS["exact"],
    "ne": _LOOKUPS["ne"],
    "gt": _LOOKUPS["gt"],
    "gte": _LOOKUPS["gte"],
    "lt": _LOOKUPS["lt"],
    "lte": _LOOKUPS["lte"],
    "like": lambda c, v: c.like(v),
    "ilike": lambda c, v: c.ilike(v),
    "contains": _LOOKUPS["contains"],
    "icontains": _LOOKUPS["icontains"],
    "startswith": _LOOKUPS["startswith"],
    "endswith": _LOOKUPS["endswith"],
    "in": _LOOKUPS["in"],
    "not_in": _LOOKUPS["not_in"],
    "is_null": lambda c, v: c.is_(None),
    "is_not_null": lambda c, v: c.isnot(None),
    "between": _LOOKUPS["between"],
    "regex": _LOOKUPS["regex"],
}


@lru_cache(maxsize=512)
def _is_django_lookup(key: str) -> bool:
    """检查关键字是否为 Django 风格查询

    参数:
        key: 关键字参数名

    返回:
        bool: 是否为 Django 风格查询
    """
    return "__" in key and not key.startswith("__") and not key.endswith("__")


def _resolve_column_path(
    model_class: type, key: str
) -> tuple[Any, str, type]:
    """解析嵌套关系路径，返回最终列、lookup 类型和最终模型类

    参数:
        model_class: 起始模型类
        key: 查询键，格式如 "field__lookup" 或 "rel1__rel2__field__lookup"

    返回:
        tuple[Any, str, type]: (列对象, lookup类型, 最终模型类)

    抛出:
        AttributeError: 路径中存在无效字段或关系
    """
    parts = key.split("__")
    if len(parts) >= 2 and parts[-1] in _LOOKUPS:
        lookup, field_parts = parts[-1], parts[:-1]
    else:
        lookup, field_parts = "exact", parts

    current_model = model_class
    current_attr = None
    for idx, part in enumerate(field_parts):
        current_attr = getattr(current_model, part, None)
        if current_attr is None:
            raise AttributeError(
                f"模型 {current_model.__name__} 不存在字段或关系: {part}"
            )
        if idx == len(field_parts) - 1:
            break
        current_model = current_attr.property.mapper.class_
    return current_attr, lookup, current_model


def _parse_django_lookup(model_class: type, key: str, value: Any) -> Any:
    """解析单个 Django 风格查询条件

    参数:
        model_class: 模型类
        key: 查询键
        value: 查询值

    返回:
        Any: SQLAlchemy 过滤条件
    """
    col, lookup, _ = _resolve_column_path(model_class, key)
    builder = _LOOKUPS.get(lookup)
    return builder(col, value) if builder else col == value


def _build_django_conditions(
    model_class: type, django_kwargs: dict[str, Any]
) -> list[ColumnElement[bool]]:
    """构建 Django 风格查询条件列表

    参数:
        model_class: 模型类
        django_kwargs: Django 风格查询关键字参数

    返回:
        list[ColumnElement[bool]]: SQLAlchemy 过滤条件列表
    """
    return [_parse_django_lookup(model_class, k, v) for k, v in django_kwargs.items()]


def _separate_kwargs(
    kwargs: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """分离普通 kwargs 与 Django 风格 kwargs

    参数:
        kwargs: 混合的关键字参数

    返回:
        tuple[dict, dict]: (普通参数, Django 风格参数)
    """
    regular, django = {}, {}
    for key, value in kwargs.items():
        if _is_django_lookup(key):
            django[key] = value
        else:
            regular[key] = value
    return regular, django


def _compile_filter_args(
    model_class: type, args: tuple[Any, ...]
) -> list[ColumnElement[bool]]:
    """编译过滤参数，将 Q 对象编译为表达式，非 Q 对象直接收集

    供 ``build_filter_statement`` 与 ``QueryExecutorMixin._apply_filters``
    复用，消除 Q 对象编译逻辑的重复。

    参数:
        model_class: 模型类，用于解析字段
        args: 过滤参数元组，元素为 SQLAlchemy 表达式或 Q 对象

    返回:
        list[ColumnElement[bool]]: 编译后的条件列表
    """
    clauses: list[ColumnElement[bool]] = []
    for arg in args:
        if isinstance(arg, Q):
            compiled = arg.compile(model_class, _build_django_conditions)
            if compiled is not None:
                clauses.append(compiled)
        else:
            clauses.append(arg)
    return clauses


def build_filter_statement(model_class: type, *args: Any, **kwargs: Any) -> Select:
    """构建过滤查询语句

    供 Model 的 get_or_create、update_or_create 等类方法使用。

    参数:
        model_class: 模型类
        *args: SQLAlchemy 过滤表达式或 Q 对象
        **kwargs: 查询条件，支持 Django 风格双下划线语法

    返回:
        Select: SQLAlchemy 查询语句
    """
    stmt = select(model_class)
    if kwargs:
        regular, django = _separate_kwargs(kwargs)
        if regular:
            stmt = stmt.filter_by(**regular)
        if django:
            stmt = stmt.where(*_build_django_conditions(model_class, django))
    if args:
        clauses = _compile_filter_args(model_class, args)
        if clauses:
            stmt = stmt.where(*clauses)
    return stmt


def _is_retryable_error(error: Exception) -> bool:
    """判断错误是否可重试

    参数:
        error: 异常对象

    返回:
        bool: 是否可重试
    """
    if not isinstance(error, _RETRYABLE_ERRORS):
        return False
    error_msg = str(error).lower()
    return not any(kw in error_msg for kw in _NON_RETRYABLE_KEYWORDS)


class Q:
    """Django 风格的查询条件组合对象

    支持基本查询条件、逻辑与或非组合，可用于 QueryWrapper.filter 等方法。

    示例:
        Q(name__contains="test")
        Q(status=1) | Q(status=2)
        ~Q(is_deleted=True)
    """

    __slots__ = ("_args", "_children", "_kwargs", "_negated", "_operator")

    def __init__(self, *args: ColumnElement[bool] | "Q", **kwargs: Any):
        """初始化 Q 对象

        参数:
            *args: SQLAlchemy 条件表达式或其他 Q 对象
            **kwargs: Django 风格或普通等值查询条件
        """
        self._args: tuple[ColumnElement[bool] | "Q", ...] = args
        self._kwargs: dict[str, Any] = kwargs
        self._negated: bool = False
        self._operator: str = "AND"
        self._children: list["Q"] = []

    def __and__(self, other: "Q") -> "Q":
        """逻辑与组合"""
        return self._combine(other, "AND")

    def __or__(self, other: "Q") -> "Q":
        """逻辑或组合"""
        return self._combine(other, "OR")

    def __invert__(self) -> "Q":
        """逻辑非组合，返回新的取反 Q 对象"""
        q = Q()
        q._args = self._args
        q._kwargs = self._kwargs
        q._negated = not self._negated
        q._operator = self._operator
        q._children = self._children
        return q

    def _combine(self, other: "Q", operator: str) -> "Q":
        """组合两个 Q 对象

        参数:
            other: 另一个 Q 对象
            operator: 逻辑操作符，"AND" 或 "OR"

        返回:
            Q: 新的组合 Q 对象
        """
        q = Q()
        q._operator = operator
        q._children = [self, other]
        return q

    def compile(
        self,
        model_class: type,
        build_conditions_fn: Callable[
            [type, dict[str, Any]], list[ColumnElement[bool]]
        ],
    ) -> ColumnElement[bool] | None:
        """将 Q 对象编译为 SQLAlchemy 条件表达式

        参数:
            model_class: 模型类，用于解析字段
            build_conditions_fn: 将 kwargs 转换为条件列表的函数

        返回:
            ColumnElement[bool] | None: 编译后的条件表达式，空 Q 返回 None
        """
        # 绝不能对表达式对象做真值过滤（filter(None, ...) 或 if clause）：
        # 部分 SQLAlchemy 版本中 Comparison/BinaryExpression 布尔求值为 False，
        # 会静默丢弃全部 Q 条件导致查询退化为全表
        if self._children:
            clauses = [
                child
                for child in (
                    child_.compile(model_class, build_conditions_fn)
                    for child_ in self._children
                )
                if child is not None
            ]
            if not clauses:
                return None
            clause = and_(*clauses) if self._operator == "AND" else or_(*clauses)
        else:
            conditions = build_conditions_fn(model_class, self._kwargs)
            if not conditions:
                return None
            clause = and_(*conditions)
            for arg in self._args:
                if isinstance(arg, Q):
                    compiled = arg.compile(model_class, build_conditions_fn)
                    if compiled is not None:
                        clause = and_(clause, compiled)
                else:
                    clause = and_(clause, arg)
        return not_(clause) if self._negated else clause
