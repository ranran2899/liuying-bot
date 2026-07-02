"""基础查询构建方法模块"""

from typing import Any, Self

from sqlalchemy import ColumnElement, func

from ..utils import DbUtils


class BaseQueryBuilder:
    """基础查询构建器，提供链式调用的查询构建方法"""

    __slots__ = ()

    model_class: type
    _limit: int | None
    _offset: int | None
    _order_by: tuple[Any, ...] | None
    _distinct: bool
    _join_conditions: list[dict[str, Any]]
    _group_by: tuple[Any, ...] | None
    _having: Any
    _values: tuple[Any, ...] | None
    _lock_mode: str | None
    _db_name: str
    _load_relationships: list[tuple[Any, dict[str, Any]]]

    def _process_order_item(self, item: str | Any) -> Any:
        """处理单个排序项

        参数:
            item: 排序项（字符串或列对象）

        返回:
            排序后的列对象
        """
        if isinstance(item, str):
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
        return item

    def limit(self, limit: int) -> Self:
        """设置查询结果数量限制

        参数:
            limit: 限制数量

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        self._limit = limit
        return self

    def offset(self, offset: int) -> Self:
        """设置查询结果偏移量

        参数:
            offset: 偏移量

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        self._offset = offset
        return self

    def order_by(self, *order_by: str | Any) -> Self:
        """设置排序条件

        支持格式: "-字段名"降序, "字段名"升序, "字段名 DESC/ASC", 列对象

        参数:
            *order_by: 排序条件

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        self._order_by = tuple(self._process_order_item(item) for item in order_by)
        return self

    def in_random_order(self) -> Self:
        """随机排序查询结果

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        self._order_by = (func.random(),)
        return self

    def filter(self, *args: ColumnElement[bool] | Any, **kwargs: Any) -> Self:
        """添加过滤条件

        参数:
            *args: 过滤条件，支持 SQLAlchemy 表达式或 Q 对象
            **kwargs: 过滤条件，支持 Django 风格双下划线语法

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        self.args = self.args + args
        self.kwargs.update(kwargs)
        return self

    def distinct(self) -> Self:
        """设置去重查询结果

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        self._distinct = True
        return self

    def join(
        self,
        target: Any,
        onclause: Any = None,
    ) -> Self:
        """添加表连接条件

        参数:
            target: 要连接的表
            onclause: 连接条件

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        self._join_conditions.append({"target": target, "onclause": onclause})
        return self

    def group_by(self, *criterion: Any) -> Self:
        """设置分组条件

        参数:
            *criterion: 分组条件

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        self._group_by = criterion
        return self

    def having(self, criterion: Any) -> Self:
        """设置分组后的过滤条件

        参数:
            criterion: 过滤条件

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        self._having = criterion
        return self

    def values(self, *columns: str | Any) -> Self:
        """指定查询字段

        参数:
            *columns: 要查询的字段

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        self._values = columns
        return self

    def annotate(self, **annotations: ColumnElement[Any]) -> Self:
        """添加聚合标注

        参数:
            **annotations: 标注名称与聚合表达式

        返回:
            QueryWrapper: 返回自身以支持链式调用

        示例:
            Model.filter().annotate(total=func.count('*'))
        """
        self._annotations = annotations
        return self

    def defer(self, *fields: str | Any) -> Self:
        """延迟加载指定字段

        参数:
            *fields: 要延迟加载的字段名或列属性

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        self._deferred_fields = [
            DbUtils.get_column(self.model_class, field)
            if isinstance(field, str)
            else field
            for field in fields
        ]
        return self

    def select_for_update(
        self,
        nowait: bool = False,
        skip_locked: bool = False,
        read: bool = False,
        key_share: bool = False,
    ) -> Self:
        """添加 SELECT FOR UPDATE 行锁

        参数:
            nowait: 是否使用 NOWAIT
            skip_locked: 是否跳过已锁定行
            read: 是否使用 FOR SHARE 模式
            key_share: 是否使用 KEY SHARE 模式

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        self._for_update_options = {
            "nowait": nowait,
            "skip_locked": skip_locked,
            "read": read,
            "key_share": key_share,
        }
        return self

    def lock(self, mode: str = "FOR UPDATE") -> Self:
        """添加行级锁（兼容旧 API）

        参数:
            mode: 锁模式，默认为"FOR UPDATE"

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        self._lock_mode = mode
        return self

    def only(self, *fields: str) -> Self:
        """只查询指定字段

        参数:
            *fields: 要查询的字段

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        self._values = tuple(DbUtils.get_column(self.model_class, f) for f in fields)
        return self

    def except_(self, *fields: str) -> Self:
        """排除指定字段查询

        参数:
            *fields: 要排除的字段名

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        self._values = tuple(
            col for col in self.model_class.__table__.columns if col.name not in fields
        )
        return self

    def using(self, db_name: str) -> Self:
        """指定要使用的数据库名称

        参数:
            db_name: 数据库名称

        返回:
            QueryWrapper: 返回自身以支持链式调用
        """
        self._db_name = db_name
        return self
