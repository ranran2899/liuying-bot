"""查询执行和聚合方法模块"""

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import exists as sqlalchemy_exists
from sqlalchemy import func, select, text

from ..utils import DbUtils


class QueryExecutionBuilder:
    """查询执行和聚合方法构建器"""

    __slots__ = ()

    model_class: type
    _limit: int | None
    _offset: int | None
    _db_name: str
    _values: tuple[Any, ...] | None
    _annotations: dict[str, Any] | None
    _compound_stmt: Any

    def _returns_rows(self) -> bool:
        """判断查询结果是否应返回 Row 而非模型实例

        返回:
            bool: 当指定了 values、annotate 或复合查询时返回 True
        """
        return bool(
            self._values is not None
            or getattr(self, "_annotations", None)
            or getattr(self, "_compound_stmt", None)
        )

    async def first(self) -> Any | None:
        """获取查询结果的第一条记录

        返回:
            第一条记录，如果没有则返回None
        """
        stmt = self._build_base_query().limit(1)
        if self._returns_rows():
            return await self._execute_query(stmt, "first_row")
        return await self._execute_query(stmt, "first")

    async def first_or_none(self) -> Any | None:
        """获取查询结果的第一条记录，语义化别名

        返回:
            第一条记录，如果没有则返回None
        """
        return await self.first()

    async def earliest(self, field: str | None = None) -> Any | None:
        """按指定字段升序取第一条记录

        参数:
            field: 排序字段，未指定时回退到 "id"

        返回:
            第一条记录，如果没有则返回None
        """
        return await self.order_by(field or "id").first()

    async def latest(self, field: str | None = None) -> Any | None:
        """按指定字段降序取第一条记录

        参数:
            field: 排序字段，未指定时回退到 "id"

        返回:
            第一条记录，如果没有则返回None
        """
        return await self.order_by(f"-{field or 'id'}").first()

    async def all(self) -> list[Any]:
        """获取查询结果的所有记录

        返回:
            所有记录的列表
        """
        stmt = self._build_base_query()
        if self._limit:
            stmt = stmt.limit(self._limit)
        if self._offset:
            stmt = stmt.offset(self._offset)
        if self._returns_rows():
            return await self._execute_query(stmt, "fetchall")
        return await self._execute_query(stmt, "all")

    def _build_count_query(self) -> select:
        """构建计数查询语句

        返回:
            Select: 计数查询语句
        """
        stmt = select(func.count(self.model_class.id))
        return self._apply_filters(stmt)

    async def count(self) -> int:
        """获取查询结果的记录数

        返回:
            记录数量
        """
        stmt = self._build_count_query()
        return await self._execute_query(stmt, "count")

    async def exists(self) -> bool:
        """检查是否存在符合条件的记录

        返回:
            bool: 如果存在记录返回True
        """
        stmt = self._build_base_query()
        if stmt.whereclause is not None:
            exists_stmt = select(sqlalchemy_exists().where(stmt.whereclause))
        else:
            exists_stmt = select(sqlalchemy_exists().select_from(self.model_class))
        return await self._execute_query(exists_stmt, "scalar")

    async def get(self, pk: Any) -> Any | None:
        """根据主键获取单个记录

        参数:
            pk: 主键值

        返回:
            单个记录对象，如果不存在则返回None
        """
        stmt = self._build_base_query()
        stmt = stmt.where(self.model_class.id == pk)
        return await self._execute_query(stmt.limit(1), "first")

    async def find_by(self, **kwargs: Any) -> Any | None:
        """根据指定条件查找单个记录

        参数:
            **kwargs: 查询条件

        返回:
            匹配的单个记录对象
        """
        return await self.filter(**kwargs).first()

    async def find_all(self, **kwargs: Any) -> list[Any]:
        """根据指定条件查找所有记录

        参数:
            **kwargs: 查询条件

        返回:
            匹配的所有记录列表
        """
        return await self.filter(**kwargs).all()

    async def paginate(
        self,
        page: int = 1,
        per_page: int = 20,
    ) -> dict[str, Any]:
        """分页查询

        参数:
            page: 页码，从1开始
            per_page: 每页记录数

        返回:
            dict: 包含分页信息的字典
        """
        offset = (page - 1) * per_page
        total = await self.count()
        self._limit = per_page
        self._offset = offset
        items = await self.all()
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        }

    async def aggregate(
        self,
        *aggregations: Any,
        **named_aggregations: Any,
    ) -> Any:
        """聚合查询

        参数:
            *aggregations: 聚合函数列表
            **named_aggregations: 命名聚合，如 total=func.count('*')

        返回:
            命名聚合时返回 dict[str, 值]，否则返回第一行 Row
        """
        if named_aggregations:
            cols = list(aggregations) + [
                expr.label(name) for name, expr in named_aggregations.items()
            ]
            stmt = self._build_base_query(select(*cols))
            row = await self._execute_query(stmt, "first_row")
            return dict(row._mapping) if row else {}
        stmt = self._build_base_query(select(*aggregations))
        return await self._execute_query(stmt, "first_row")

    async def pluck(self, column: str | Any) -> list[Any]:
        """获取单个列的值列表

        参数:
            column: 列名或列对象

        返回:
            list: 指定列的值列表
        """
        column = DbUtils.get_column(self.model_class, column)
        stmt = self._build_base_query(select(column))
        result = await self._execute_query(stmt, "fetchall")
        return [row[0] for row in result]

    async def values_list(
        self,
        *fields: str,
        flat: bool = False,
    ) -> list[Any] | list[tuple]:
        """获取指定列的值列表

        参数:
            *fields: 列名列表
            flat: 如果为True且只指定一个字段，则返回扁平列表

        返回:
            list: 指定列的值列表或元组列表
        """
        if not fields:
            stmt = self._build_base_query()
        else:
            columns = [DbUtils.get_column(self.model_class, field) for field in fields]
            stmt = self._build_base_query(select(*columns))

        result = await self._execute_query(stmt, "fetchall")
        if flat and len(fields) == 1:
            return [row[0] for row in result]
        return result

    async def to_dict(
        self,
        only: list[str] | None = None,
        except_: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """将查询结果转换为字典列表

        参数:
            only: 只包含指定的字段列表
            except_: 排除指定的字段列表

        返回:
            list: 字典形式的记录列表
        """
        results = await self.all()
        dict_results: list[dict[str, Any]] = []

        only_set = set(only) if only else None
        except_set = set(except_) if except_ else None

        for result in results:
            table = getattr(result, "__table__", None)
            if table is None:
                dict_results.append(result)
                continue

            data: dict[str, Any] = {}
            for column in table.columns.keys():
                if only_set and column not in only_set:
                    continue
                if except_set and column in except_set:
                    continue
                data[column] = getattr(result, column)
            dict_results.append(data)

        return dict_results

    async def explain(self) -> list[Any]:
        """获取查询执行计划

        返回:
            list: 执行计划结果列表
        """
        stmt = self._build_base_query()
        explain_stmt = select(text("EXPLAIN")).select_from(stmt.subquery())
        async with self.model_class.get_session(db_name=self._db_name) as session:
            result = await session.execute(explain_stmt)
            return result.fetchall()

    async def raw(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """执行原始SQL语句

        警告:
            此方法允许执行任意SQL语句，存在SQL注入风险。
            请确保SQL语句中的所有用户输入都通过params参数传递，
            而不是直接拼接到SQL字符串中。

        参数:
            sql: 原始SQL语句，使用 :param 形式的命名参数
            params: SQL参数字典，用于参数化查询

        返回:
            Any: 查询结果

        抛出:
            ProgrammingError: SQL语法错误
            OperationalError: 数据库操作错误
        """
        async with self.model_class.get_session(db_name=self._db_name) as session:
            result = await session.execute(text(sql), params or {})
            return result

    async def find_in_batches(
        self,
        batch_size: int = 1000,
    ) -> AsyncGenerator[list[Any], None]:
        """分批处理大量数据

        参数:
            batch_size: 每批处理的记录数

        返回:
            AsyncGenerator: 异步生成器，每次产生一批记录
        """
        offset = 0
        while True:
            self._limit = batch_size
            self._offset = offset
            batch = await self.all()
            if not batch:
                break
            yield batch
            offset += batch_size
            if len(batch) < batch_size:
                break

    async def achunked(
        self,
        chunk_size: int = 1000,
    ) -> AsyncGenerator[list[Any], None]:
        """异步生成器分批读取数据

        参数:
            chunk_size: 每批记录数

        返回:
            AsyncGenerator: 每次产生一批记录
        """
        offset = 0
        while True:
            batch = await self.limit(chunk_size).offset(offset).all()
            if not batch:
                break
            yield batch
            offset += chunk_size
            if len(batch) < chunk_size:
                break

    async def iterator(
        self,
        chunk_size: int = 1000,
    ) -> AsyncGenerator[Any, None]:
        """流式迭代查询结果

        参数:
            chunk_size: 每次预读取的记录数

        返回:
            AsyncGenerator: 每次产生一条记录
        """
        stmt = self._build_base_query()
        if self._limit:
            stmt = stmt.limit(self._limit)
        if self._offset:
            stmt = stmt.offset(self._offset)
        stmt = stmt.execution_options(yield_per=chunk_size)

        async with self.model_class.get_session(db_name=self._db_name) as session:
            result = await session.execute(stmt)
            if self._returns_rows():
                async for row in result:
                    yield row
            else:
                async for item in result.scalars():
                    yield item

    async def in_bulk(
        self,
        id_list: list[Any],
        field_name: str = "id",
    ) -> dict[Any, Any]:
        """批量按字段值查询，返回字段值到实例的映射

        参数:
            id_list: 字段值列表
            field_name: 字段名，默认为 "id"

        返回:
            dict: {字段值: 实例} 的映射
        """
        if not id_list:
            return {}
        column = DbUtils.get_column(self.model_class, field_name)
        records = await self.filter(column.in_(id_list)).all()
        return {getattr(record, field_name): record for record in records}

    async def get_or_create(
        self,
        defaults: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[Any, bool]:
        """获取或创建记录

        参数:
            defaults: 创建时使用的默认值
            **kwargs: 查询条件

        返回:
            tuple: (实例对象, 是否新创建)
        """
        return await self.model_class.get_or_create(
            defaults=defaults, db_name=self._db_name, **kwargs
        )

    async def update_or_create(
        self,
        defaults: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[Any, bool]:
        """更新或创建记录

        参数:
            defaults: 创建/更新时使用的默认值
            **kwargs: 查询条件

        返回:
            tuple: (实例对象, 是否新创建)
        """
        return await self.model_class.update_or_create(
            defaults=defaults, db_name=self._db_name, **kwargs
        )

    async def _aggregate_column(
        self,
        column: str | Any,
        func_type: Any,
    ) -> Any:
        """聚合函数的通用方法

        参数:
            column: 列名或SQLAlchemy列对象
            func_type: SQLAlchemy聚合函数

        返回:
            Any: 聚合结果值
        """
        column = DbUtils.get_column(self.model_class, column)
        stmt = self._build_base_query(select(func_type(column)))
        return await self._execute_query(stmt, "scalar")

    async def min(self, column: str | Any) -> Any:
        """获取指定列的最小值

        参数:
            column: 列名或SQLAlchemy列对象

        返回:
            Any: 列的最小值
        """
        return await self._aggregate_column(column, func.min)

    async def max(self, column: str | Any) -> Any:
        """获取指定列的最大值

        参数:
            column: 列名或SQLAlchemy列对象

        返回:
            Any: 列的最大值
        """
        return await self._aggregate_column(column, func.max)

    async def avg(self, column: str | Any) -> float | None:
        """获取指定列的平均值

        参数:
            column: 列名或SQLAlchemy列对象

        返回:
            float: 列的平均值
        """
        return await self._aggregate_column(column, func.avg)

    async def sum(self, column: str | Any) -> Any:
        """获取指定列的总和

        参数:
            column: 列名或SQLAlchemy列对象

        返回:
            Any: 列的总和
        """
        return await self._aggregate_column(column, func.sum)
