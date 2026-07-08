"""过滤条件统一应用模块

提供 FilterMixin，统一处理 Django 风格查询、普通 kwargs、Q 对象、exclude
以及软删除、join 等过滤逻辑。
"""

from typing import TYPE_CHECKING, Any, Self

from sqlalchemy import ColumnElement, Select, and_, not_, select

from .django_style import DjangoStyleMixin
from .q import Q

if TYPE_CHECKING:
    from ..base_model import Model


class FilterMixin(DjangoStyleMixin):
    """统一过滤条件混入类

    供 QueryWrapper 和 UpdateDeleteBuilder 继承，统一处理查询过滤逻辑。
    """

    __slots__ = ()

    model_class: type["Model"]
    kwargs: dict[str, Any]
    args: tuple[Any, ...]

    def exclude(self, *args: ColumnElement[bool] | Any, **kwargs: Any) -> Self:
        """添加排除条件

        最终生成 NOT(...) 条件，等价于 SQL 中的排除逻辑。

        参数:
            *args: SQLAlchemy 条件表达式或 Q 对象
            **kwargs: Django 风格或普通等值查询条件

        返回:
            Self: 返回自身以支持链式调用
        """
        self._exclude_args = getattr(self, "_exclude_args", ()) + args
        exclude_kwargs: dict[str, Any] = getattr(self, "_exclude_kwargs", {})
        exclude_kwargs.update(kwargs)
        self._exclude_kwargs = exclude_kwargs
        return self

    def _apply_filters(self, stmt: Select) -> Select:
        """统一应用所有过滤条件

        参数:
            stmt: SQLAlchemy 查询语句

        返回:
            Select: 应用过滤条件后的查询语句
        """
        if hasattr(self.model_class, "deleted_at") and not getattr(
            self, "_with_deleted", False
        ):
            stmt = stmt.where(getattr(self.model_class, "deleted_at").is_(None))

        for join_condition in getattr(self, "_join_conditions", []):
            stmt = stmt.join(join_condition["target"], join_condition["onclause"])

        stmt = self._apply_kwargs_filters(stmt, self.kwargs)

        for arg in self.args:
            condition = self._resolve_condition_arg(arg)
            if condition is not None:
                stmt = stmt.where(condition)

        exclude_args = getattr(self, "_exclude_args", ())
        exclude_kwargs = getattr(self, "_exclude_kwargs", {})
        exclude_clauses: list[ColumnElement[bool]] = []
        for arg in exclude_args:
            condition = self._resolve_condition_arg(arg)
            if condition is not None:
                exclude_clauses.append(condition)
        if exclude_kwargs:
            exclude_clauses.extend(self._build_django_conditions(exclude_kwargs))
        if exclude_clauses:
            stmt = stmt.where(not_(and_(*exclude_clauses)))

        return stmt

    def _resolve_condition_arg(
        self, arg: Any
    ) -> ColumnElement[bool] | None:
        """解析单个条件参数

        支持 Q 对象和普通 SQLAlchemy 条件表达式。

        参数:
            arg: 条件参数

        返回:
            ColumnElement[bool] | None: 解析后的条件表达式
        """
        if isinstance(arg, Q):
            return arg.compile(self.model_class, self._build_django_conditions)
        return arg

    @staticmethod
    def _separate_kwargs(
        kwargs: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """分离普通 kwargs 与 Django 风格 kwargs

        参数:
            kwargs: 混合的关键字参数

        返回:
            tuple[dict, dict]: (普通参数, Django 风格参数)
        """
        regular: dict[str, Any] = {}
        django: dict[str, Any] = {}
        for key, value in kwargs.items():
            if DjangoStyleMixin.is_django_lookup(key):
                django[key] = value
            else:
                regular[key] = value
        return regular, django

    def _apply_kwargs_filters(self, stmt: Select, kwargs: dict[str, Any]) -> Select:
        """应用 kwargs 过滤条件

        参数:
            stmt: SQLAlchemy 查询语句
            kwargs: 混合的关键字参数

        返回:
            Select: 应用条件后的查询语句
        """
        return FilterMixin._apply_kwargs_filters_to_statement(
            stmt, self.model_class, kwargs
        )

    @staticmethod
    def _apply_kwargs_filters_to_statement(
        stmt: Select,
        model_class: type,
        kwargs: dict[str, Any],
    ) -> Select:
        """静态方法：将 kwargs 过滤条件应用到语句

        参数:
            stmt: SQLAlchemy 查询语句
            model_class: 模型类
            kwargs: 混合的关键字参数

        返回:
            Select: 应用条件后的查询语句
        """
        if not kwargs:
            return stmt
        regular_kwargs, django_kwargs = FilterMixin._separate_kwargs(kwargs)
        if regular_kwargs:
            stmt = stmt.filter_by(**regular_kwargs)
        if django_kwargs:
            conditions = FilterMixin._build_django_conditions_static(
                model_class, django_kwargs
            )
            stmt = stmt.where(*conditions)
        return stmt

    def _build_django_conditions(
        self, django_kwargs: dict[str, Any]
    ) -> list[ColumnElement[bool]]:
        """构建 Django 风格查询条件列表

        参数:
            django_kwargs: Django 风格查询关键字参数

        返回:
            list[ColumnElement[bool]]: SQLAlchemy 过滤条件列表
        """
        return FilterMixin._build_django_conditions_static(
            self.model_class, django_kwargs
        )

    @staticmethod
    def _build_django_conditions_static(
        model_class: type,
        django_kwargs: dict[str, Any],
    ) -> list[ColumnElement[bool]]:
        """静态方法：构建 Django 风格查询条件列表

        参数:
            model_class: 模型类
            django_kwargs: Django 风格查询关键字参数

        返回:
            list[ColumnElement[bool]]: SQLAlchemy 过滤条件列表
        """
        return [
            DjangoStyleMixin.parse_django_lookup(model_class, k, v)
            for k, v in django_kwargs.items()
        ]

    @staticmethod
    def build_filter_statement(
        model_class: type,
        *args: Any,
        **kwargs: Any,
    ) -> Select:
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
            stmt = FilterMixin._apply_kwargs_filters_to_statement(
                stmt, model_class, kwargs
            )
        if args:
            clauses: list[ColumnElement[bool]] = []
            for arg in args:
                if isinstance(arg, Q):
                    compiled = arg.compile(
                        model_class,
                        lambda mc, dk: FilterMixin._build_django_conditions_static(
                            mc, dk
                        ),
                    )
                    if compiled is not None:
                        clauses.append(compiled)
                else:
                    clauses.append(arg)
            if clauses:
                stmt = stmt.where(*clauses)
        return stmt
