"""Django 风格 Q 对象实现模块

提供支持 AND、OR、NOT 组合的查询条件对象，可嵌套使用。
"""

from collections.abc import Callable
from typing import Any, Self

from sqlalchemy import ColumnElement, and_, not_, or_


class Q:
    """Django 风格的查询条件组合对象

    支持基本查询条件、逻辑与或非组合，可用于 QueryWrapper.filter 等方法的
    *args 中传入复杂条件。

    示例:
        Q(name__contains="test")
        Q(status=1) | Q(status=2)
        ~Q(is_deleted=True)
        Q(Q(name="a") & Q(name="b"))
    """

    __slots__ = ("_args", "_children", "_kwargs", "_negated", "_operator")

    def __init__(self, *args: ColumnElement[bool] | Self, **kwargs: Any):
        """初始化 Q 对象

        参数:
            *args: SQLAlchemy 条件表达式或其他 Q 对象
            **kwargs: Django 风格或普通等值查询条件
        """
        self._args: tuple[ColumnElement[bool] | Self, ...] = args
        self._kwargs: dict[str, Any] = kwargs
        self._negated: bool = False
        self._operator: str = "AND"
        self._children: list[Self] = []

    def __and__(self, other: Self) -> Self:
        """逻辑与组合"""
        return self._combine(other, "AND")

    def __or__(self, other: Self) -> Self:
        """逻辑或组合"""
        return self._combine(other, "OR")

    def __invert__(self) -> Self:
        """逻辑非组合，返回新的取反 Q 对象"""
        q = Q()
        q._args = self._args
        q._kwargs = self._kwargs
        q._negated = not self._negated
        q._operator = self._operator
        q._children = self._children
        return q

    def _combine(self, other: Self, operator: str) -> Self:
        """组合两个 Q 对象

        参数:
            other: 另一个 Q 对象
            operator: 逻辑操作符，"AND" 或 "OR"

        返回:
            Self: 新的组合 Q 对象
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
        if self._children:
            clauses = [
                child.compile(model_class, build_conditions_fn)
                for child in self._children
            ]
            clauses = [c for c in clauses if c is not None]
            if not clauses:
                return None
            clause = or_(*clauses) if self._operator == "OR" else and_(*clauses)
        else:
            clauses: list[ColumnElement[bool]] = []
            for arg in self._args:
                if isinstance(arg, Q):
                    compiled = arg.compile(model_class, build_conditions_fn)
                    if compiled is not None:
                        clauses.append(compiled)
                else:
                    clauses.append(arg)
            if self._kwargs:
                clauses.extend(build_conditions_fn(model_class, self._kwargs))
            if not clauses:
                return None
            clause = and_(*clauses) if len(clauses) > 1 else clauses[0]

        return not_(clause) if self._negated else clause
