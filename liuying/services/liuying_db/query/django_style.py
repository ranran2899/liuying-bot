"""Django风格查询语法支持模块

提供将Django ORM风格的双下划线查询语法转换为SQLAlchemy过滤条件的功能。
通过DjangoStyleMixin混入类，让QueryWrapper和UpdateDeleteBuilder继承使用。

支持的查询语法:
    - exact: 精确匹配 (field__exact=value)
    - iexact: 不区分大小写精确匹配 (field__iexact=value)
    - contains: 包含 (field__contains=value)
    - icontains: 不区分大小写包含 (field__icontains=value)
    - startswith: 前缀匹配 (field__startswith=value)
    - istartswith: 不区分大小写前缀匹配 (field__istartswith=value)
    - endswith: 后缀匹配 (field__endswith=value)
    - iendswith: 不区分大小写后缀匹配 (field__iendswith=value)
    - gt: 大于 (field__gt=value)
    - gte: 大于等于 (field__gte=value)
    - lt: 小于 (field__lt=value)
    - lte: 小于等于 (field__lte=value)
    - in: 包含于列表 (field__in=[v1, v2])
    - not_in: 不包含于列表 (field__not_in=[v1, v2])
    - range: 范围查询 (field__range=(start, end))
    - between: BETWEEN查询 (field__between=(start, end))
    - isnull: 为空/非空 (field__isnull=True/False)
    - regex: 正则匹配 (field__regex=pattern)
    - iregex: 不区分大小写正则匹配 (field__iregex=pattern)
    - year/month/day: 年/月/日提取 (field__year=2024)
    - hour/minute/second: 时/分/秒提取
    - week_day: 星期几提取（PostgreSQL为dow，其他方言可能不同）
    - date: 日期部分匹配 (field__date="2024-01-01")
    - time: 时间部分匹配 (field__time="12:00:00")
    - search: 全文搜索 (field__search="keyword")

同时支持嵌套关系路径，例如 user__group__name__icontains。
"""

from typing import TYPE_CHECKING, Any, ClassVar

from sqlalchemy import Date, Time, and_, cast, func

if TYPE_CHECKING:
    from sqlalchemy.orm import RelationshipProperty

    from ..base_model import Model


class DjangoStyleMixin:
    """Django风格查询语法混入类

    提供Django风格双下划线查询语法的解析和转换能力，
    只负责单个lookup的解析，过滤条件的应用由FilterMixin处理。
    """

    __slots__ = ()

    @staticmethod
    def _escape_like(value: str) -> str:
        """转义LIKE查询中的特殊字符

        参数:
            value: 原始字符串

        返回:
            str: 转义后的字符串
        """
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    @staticmethod
    def _build_exact(col: Any, value: Any) -> Any:
        return col == value

    @staticmethod
    def _build_iexact(col: Any, value: Any) -> Any:
        return col.ilike(DjangoStyleMixin._escape_like(str(value)), escape="\\")

    @staticmethod
    def _build_contains(col: Any, value: Any) -> Any:
        return col.like(
            f"%{DjangoStyleMixin._escape_like(str(value))}%", escape="\\"
        )

    @staticmethod
    def _build_icontains(col: Any, value: Any) -> Any:
        return col.ilike(
            f"%{DjangoStyleMixin._escape_like(str(value))}%", escape="\\"
        )

    @staticmethod
    def _build_startswith(col: Any, value: Any) -> Any:
        return col.like(
            f"{DjangoStyleMixin._escape_like(str(value))}%", escape="\\"
        )

    @staticmethod
    def _build_istartswith(col: Any, value: Any) -> Any:
        return col.ilike(
            f"{DjangoStyleMixin._escape_like(str(value))}%", escape="\\"
        )

    @staticmethod
    def _build_endswith(col: Any, value: Any) -> Any:
        return col.like(
            f"%{DjangoStyleMixin._escape_like(str(value))}", escape="\\"
        )

    @staticmethod
    def _build_iendswith(col: Any, value: Any) -> Any:
        return col.ilike(
            f"%{DjangoStyleMixin._escape_like(str(value))}", escape="\\"
        )

    @staticmethod
    def _build_gt(col: Any, value: Any) -> Any:
        return col > value

    @staticmethod
    def _build_gte(col: Any, value: Any) -> Any:
        return col >= value

    @staticmethod
    def _build_lt(col: Any, value: Any) -> Any:
        return col < value

    @staticmethod
    def _build_lte(col: Any, value: Any) -> Any:
        return col <= value

    @staticmethod
    def _build_ne(col: Any, value: Any) -> Any:
        return col != value

    @staticmethod
    def _build_in(col: Any, value: Any) -> Any:
        return col.in_(value)

    @staticmethod
    def _build_not_in(col: Any, value: Any) -> Any:
        return col.notin_(value)

    @staticmethod
    def _build_range(col: Any, value: Any) -> Any:
        return and_(col >= value[0], col <= value[1])

    @staticmethod
    def _build_between(col: Any, value: Any) -> Any:
        return col.between(value[0], value[1])

    @staticmethod
    def _build_isnull(col: Any, value: Any) -> Any:
        return col.is_(None) if value else col.isnot(None)

    @staticmethod
    def _build_regex(col: Any, value: Any) -> Any:
        return col.regexp_match(value)

    @staticmethod
    def _build_iregex(col: Any, value: Any) -> Any:
        return col.regexp_match(value, flags="i")

    @staticmethod
    def _build_year(col: Any, value: Any) -> Any:
        return func.extract("year", col) == value

    @staticmethod
    def _build_month(col: Any, value: Any) -> Any:
        return func.extract("month", col) == value

    @staticmethod
    def _build_day(col: Any, value: Any) -> Any:
        return func.extract("day", col) == value

    @staticmethod
    def _build_hour(col: Any, value: Any) -> Any:
        return func.extract("hour", col) == value

    @staticmethod
    def _build_minute(col: Any, value: Any) -> Any:
        return func.extract("minute", col) == value

    @staticmethod
    def _build_second(col: Any, value: Any) -> Any:
        return func.extract("second", col) == value

    @staticmethod
    def _build_week_day(col: Any, value: Any) -> Any:
        """星期几查询

        使用 PostgreSQL 的 dow（0=周日）。不同数据库方言对星期的定义可能不同，
        调用方需根据实际数据库调整 value 的取值。
        """
        return func.extract("dow", col) == value

    @staticmethod
    def _build_date(col: Any, value: Any) -> Any:
        return cast(col, Date) == value

    @staticmethod
    def _build_time(col: Any, value: Any) -> Any:
        return cast(col, Time) == value

    @staticmethod
    def _build_search(col: Any, value: Any) -> Any:
        return col.match(value)

    _LOOKUPS: ClassVar[dict[str, Any]] = {}

    @staticmethod
    def is_django_lookup(key: str) -> bool:
        """检查关键字参数是否为Django风格查询

        只要包含双下划线（且不以下划线开头/结尾）即视为 Django 风格路径，
        由 _resolve_column_path 解析具体 lookup。

        参数:
            key: 关键字参数名

        返回:
            bool: 是否为Django风格查询
        """
        return "__" in key and not key.startswith("__") and not key.endswith("__")

    @staticmethod
    def _resolve_column_path(
        model_class: type["Model"],
        key: str,
    ) -> tuple[Any, str, type["Model"]]:
        """解析嵌套关系路径，返回最终列、lookup类型、最终模型类

        参数:
            model_class: 起始模型类
            key: 查询键，格式如 "field__lookup" 或 "rel1__rel2__field__lookup"

        返回:
            tuple[Any, str, type[Model]]: (列对象, lookup类型, 最终模型类)

        抛出:
            AttributeError: 路径中存在无效字段或关系
        """
        parts = key.split("__")

        if len(parts) >= 2 and parts[-1] in DjangoStyleMixin._LOOKUPS:
            lookup = parts[-1]
            field_parts = parts[:-1]
        else:
            lookup = "exact"
            field_parts = parts

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

            prop: RelationshipProperty = current_attr.property
            current_model = prop.mapper.class_

        return current_attr, lookup, current_model

    @staticmethod
    def parse_django_lookup(
        model_class: type["Model"],
        key: str,
        value: Any,
    ) -> Any:
        """解析单个Django风格查询条件

        参数:
            model_class: 模型类
            key: 查询键，支持嵌套关系路径如 "user__group__name__icontains"
            value: 查询值

        返回:
            Any: SQLAlchemy过滤条件
        """
        col, lookup, _ = DjangoStyleMixin._resolve_column_path(model_class, key)
        builder = DjangoStyleMixin._LOOKUPS.get(lookup)
        if builder is None:
            return col == value
        return builder(col, value)


DjangoStyleMixin._LOOKUPS = {
    "exact": DjangoStyleMixin._build_exact,
    "iexact": DjangoStyleMixin._build_iexact,
    "contains": DjangoStyleMixin._build_contains,
    "icontains": DjangoStyleMixin._build_icontains,
    "startswith": DjangoStyleMixin._build_startswith,
    "istartswith": DjangoStyleMixin._build_istartswith,
    "endswith": DjangoStyleMixin._build_endswith,
    "iendswith": DjangoStyleMixin._build_iendswith,
    "gt": DjangoStyleMixin._build_gt,
    "gte": DjangoStyleMixin._build_gte,
    "lt": DjangoStyleMixin._build_lt,
    "lte": DjangoStyleMixin._build_lte,
    "ne": DjangoStyleMixin._build_ne,
    "in": DjangoStyleMixin._build_in,
    "not_in": DjangoStyleMixin._build_not_in,
    "range": DjangoStyleMixin._build_range,
    "between": DjangoStyleMixin._build_between,
    "isnull": DjangoStyleMixin._build_isnull,
    "regex": DjangoStyleMixin._build_regex,
    "iregex": DjangoStyleMixin._build_iregex,
    "year": DjangoStyleMixin._build_year,
    "month": DjangoStyleMixin._build_month,
    "day": DjangoStyleMixin._build_day,
    "hour": DjangoStyleMixin._build_hour,
    "minute": DjangoStyleMixin._build_minute,
    "second": DjangoStyleMixin._build_second,
    "week_day": DjangoStyleMixin._build_week_day,
    "date": DjangoStyleMixin._build_date,
    "time": DjangoStyleMixin._build_time,
    "search": DjangoStyleMixin._build_search,
}
