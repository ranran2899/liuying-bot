"""查询构建器模块

提供链式调用的查询接口，整合 Django 风格查询语法、Q 对象条件组合、
查询执行、聚合统计与批量修改操作。

核心导出:
    - ``Q``: Django 风格查询条件组合对象，支持 AND/OR/NOT
    - ``QueryWrapper``: 链式查询构建器，支持过滤、排序、分页、聚合等
    - ``build_filter_statement``: 构建 SQLAlchemy 过滤查询语句的工具函数

模块结构:
    - ``conditions``: Q 类、查询条件构建工具函数与常量
    - ``builder``: QueryBuilderMixin，链式构建与 where_* 条件方法
    - ``executor``: QueryExecutorMixin，查询执行、聚合与批量操作
"""

from typing import TYPE_CHECKING, Any

from .builder import QueryBuilderMixin
from .conditions import Q, build_filter_statement, query_cache_namespace
from .executor import QueryExecutorMixin

if TYPE_CHECKING:
    from ..base_model import Model


class QueryWrapper[T: Model](QueryBuilderMixin[T], QueryExecutorMixin[T]):
    """链式查询构建器

    提供完整的查询构建、执行、聚合与批量修改能力。
    支持 Django 风格双下划线查询语法和 Q 对象条件组合。

    类型参数:
        T: 模型类型，必须继承自 Model 基类

    使用示例:
        results = await Model.filter(status=1)\\
            .where_gt("created_at", "2024-01-01")\\
            .order_by("-created_at")\\
            .limit(10)\\
            .all()
    """

    __slots__ = (
        "_annotations",
        "_cache_key",
        "_cache_ttl",
        "_db_name",
        "_deferred_fields",
        "_distinct",
        "_exclude_args",
        "_exclude_kwargs",
        "_for_update_options",
        "_group_by",
        "_having",
        "_join_conditions",
        "_limit",
        "_load_relationships",
        "_offset",
        "_order_by",
        "_values",
        "_with_deleted",
        "args",
        "kwargs",
        "model_class",
    )

    def __init__(
        self,
        model_class: type[T],
        *args: Any,
        skip_none: bool = False,
        **kwargs: Any,
    ):
        """初始化查询包装器

        参数:
            model_class: 模型类
            *args: 查询条件
            skip_none: 为True时忽略值为None的kwargs条件
            **kwargs: 查询条件
        """
        self.model_class = model_class
        self.args: tuple[Any, ...] = args
        self.kwargs: dict[str, Any] = (
            {k: v for k, v in kwargs.items() if v is not None} if skip_none else kwargs
        )
        self._limit: int | None = None
        self._offset: int | None = None
        self._order_by: tuple[Any, ...] | None = None
        self._distinct: bool = False
        self._join_conditions: list[dict[str, Any]] = []
        self._group_by: tuple[Any, ...] | None = None
        self._having: Any = None
        self._values: tuple[Any, ...] | None = None
        self._db_name: str = "default"
        self._with_deleted: bool = False
        self._cache_key: str | None = None
        self._cache_ttl: int | None = None
        self._annotations: dict[str, Any] | None = None
        self._deferred_fields: list[Any] = []
        self._for_update_options: dict[str, bool] | None = None
        self._load_relationships: list[tuple[Any, dict[str, Any]]] = []
        self._exclude_args: tuple[Any, ...] = ()
        self._exclude_kwargs: dict[str, Any] = {}


__all__ = [
    "Q",
    "QueryWrapper",
    "build_filter_statement",
    "query_cache_namespace",
]
