"""查询执行器 Mixin

提供查询执行、聚合统计与批量修改操作能力，包含内部查询构建
辅助方法、异步执行方法和批量操作方法族。

由 ``QueryWrapper`` 组合使用，不单独实例化。
"""

import asyncio
from collections.abc import AsyncGenerator, Callable
from datetime import datetime
import hashlib
import itertools
import time
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    and_,
    delete,
    func,
    not_,
    select,
    text,
    update,
)
from sqlalchemy.orm import defer, joinedload, selectinload
from sqlalchemy.sql.selectable import Select

from liuying.services.cache import Cache
from liuying.utils.log import logger

from ..config import LOG_COMMAND, SLOW_QUERY_THRESHOLD
from ..utils import DbUtils
from .conditions import (
    _BASE_DELAY,
    _MAX_RETRIES,
    _QUERY_CACHE,
    _RESULT_HANDLERS,
    _RETRYABLE_ERRORS,
    _build_django_conditions,
    _compile_filter_args,
    _is_retryable_error,
    _separate_kwargs,
    query_cache_namespace,
)

if TYPE_CHECKING:
    from . import QueryWrapper


class QueryExecutorMixin:
    """查询执行与修改操作方法集合

    提供查询执行、聚合统计、批量修改操作和内部查询构建辅助方法。
    """

    # ========== 查询构建内部方法 ==========

    @property
    def _cache_enabled(self) -> bool:
        """缓存是否启用"""
        return self._cache_ttl is not None and self._cache_ttl > 0

    async def _invalidate_write_cache(self) -> None:
        """写操作后失效缓存：按模型命名空间清除查询缓存，并清除模型主键缓存"""
        await self.model_class._invalidate_query_cache()
        cache_type = getattr(self.model_class, "cache_type", None)
        if cache_type:
            try:
                await Cache(cache_type, result_type=self.model_class).clear()
            except Exception as e:
                logger.warning(f"清除模型缓存失败: {e}", LOG_COMMAND)

    def _returns_rows(self) -> bool:
        """判断查询结果是否应返回 Row 而非模型实例"""
        return bool(self._values is not None or self._annotations)

    def _apply_filters(self, stmt: Select) -> Select:
        """统一应用所有过滤条件

        参数:
            stmt: SQLAlchemy 查询语句

        返回:
            Select: 应用过滤条件后的查询语句
        """
        if hasattr(self.model_class, "deleted_at") and not self._with_deleted:
            stmt = stmt.where(getattr(self.model_class, "deleted_at").is_(None))

        for join_cond in self._join_conditions:
            stmt = stmt.join(join_cond["target"], join_cond["onclause"])

        # 应用 kwargs 过滤
        if self.kwargs:
            regular, django = _separate_kwargs(self.kwargs)
            if regular:
                stmt = stmt.filter_by(**regular)
            if django:
                stmt = stmt.where(*_build_django_conditions(self.model_class, django))

        # 应用 args 条件
        clauses = _compile_filter_args(self.model_class, self.args)
        if clauses:
            stmt = stmt.where(*clauses)

        # 应用排除条件
        exclude_clauses = _compile_filter_args(self.model_class, self._exclude_args)
        if self._exclude_kwargs:
            exclude_clauses.extend(
                _build_django_conditions(self.model_class, self._exclude_kwargs)
            )
        if exclude_clauses:
            stmt = stmt.where(not_(and_(*exclude_clauses)))
        return stmt

    def _apply_order_limit(self, stmt: Select) -> Select:
        """应用排序、分组、锁等条件"""
        if self._order_by:
            stmt = stmt.order_by(*self._order_by)
        if self._distinct:
            stmt = stmt.distinct()
        if self._group_by:
            stmt = stmt.group_by(*self._group_by)
        if self._having is not None:
            stmt = stmt.having(self._having)
        if self._limit is not None:
            stmt = stmt.limit(self._limit)
        if self._offset is not None:
            stmt = stmt.offset(self._offset)
        if self._for_update_options:
            stmt = stmt.with_for_update(
                nowait=self._for_update_options["nowait"],
                skip_locked=self._for_update_options["skip_locked"],
                read=self._for_update_options["read"],
                key_share=self._for_update_options["key_share"],
            )
        return stmt

    def _apply_relationship_load_options(self, stmt: Select) -> Select:
        """应用关联关系加载选项"""
        for relationship, options in self._load_relationships:
            strategy = options.get("strategy", "selectin")
            if isinstance(relationship, str):
                parts = relationship.split(".")
                current = getattr(self.model_class, parts[0])
                for part in parts[1:]:
                    current = getattr(current.property.mapper.class_, part)
                relationship = current
            loader = (
                joinedload(relationship)
                if strategy == "joined"
                else selectinload(relationship)
            )
            stmt = stmt.options(loader)
        return stmt

    def _build_base_query(self, stmt: Select | None = None) -> Select:
        """构建基础查询语句

        参数:
            stmt: 可选的基础语句，未指定时使用 select(model_class)

        返回:
            Select: 构建完成的查询语句
        """
        if stmt is None:
            stmt = select(self.model_class)
        stmt = self._apply_filters(stmt)
        stmt = self._apply_order_limit(stmt)
        stmt = self._apply_relationship_load_options(stmt)
        if self._deferred_fields:
            stmt = stmt.options(defer(*self._deferred_fields))
        if self._values:
            stmt = stmt.with_only_columns(*self._values)
        if self._annotations:
            for name, expr in self._annotations.items():
                stmt = stmt.add_columns(expr.label(name))
        return stmt

    async def _execute_query(self, stmt: Select, fetch_type: str = "all") -> Any:
        """执行查询并返回结果，包含智能重试机制

        参数:
            stmt: 查询语句
            fetch_type: 获取结果类型

        返回:
            Any: 查询结果

        抛出:
            ValueError: 不支持的 fetch_type
        """
        if fetch_type not in _RESULT_HANDLERS:
            raise ValueError(f"不支持的fetch_type: {fetch_type}")

        cache_key = self._cache_key
        if cache_key is None and self._cache_enabled:
            # 编译产物文本 + 绑定参数共同生成摘要：
            # 仅凭 str(stmt) 不同参数值的语句文本相同，会导致不同查询
            # 互相命中对方缓存结果
            compiled = stmt.compile()
            param_repr = repr(sorted(compiled.params.items(), key=lambda kv: kv[0]))
            stmt_hash = hashlib.md5(f"{compiled}\n{param_repr}".encode()).hexdigest()
            cache_key = (
                f"{self._db_name}:{self.model_class.__name__}:{fetch_type}:{stmt_hash}"
            )

        namespace = query_cache_namespace(self.model_class)
        if self._cache_enabled and cache_key:
            try:
                cached = await _QUERY_CACHE.get(cache_key, namespace=namespace)
                if cached is not None:
                    return cached
            except Exception as e:
                logger.warning(f"缓存读取失败，降级为数据库查询: {e}", LOG_COMMAND)

        for attempt in range(_MAX_RETRIES):
            try:
                async with self.model_class.get_session(
                    db_name=self._db_name
                ) as session:
                    start = time.perf_counter()
                    result = await session.execute(stmt)
                    elapsed = time.perf_counter() - start
                    if elapsed > SLOW_QUERY_THRESHOLD:
                        logger.warning(
                            f"慢查询检测 [{self._db_name}] "
                            f"{self.model_class.__name__}.{fetch_type} "
                            f"耗时: {elapsed:.3f}s",
                            LOG_COMMAND,
                        )
                    query_result = _RESULT_HANDLERS[fetch_type](result)
                    if self._cache_enabled and cache_key:
                        try:
                            await _QUERY_CACHE.set(
                                cache_key,
                                query_result,
                                expire=self._cache_ttl,
                                namespace=namespace,
                            )
                        except Exception as e:
                            logger.warning(f"缓存写入失败: {e}", LOG_COMMAND)
                    return query_result
            except _RETRYABLE_ERRORS as e:
                if not _is_retryable_error(e):
                    raise
                if attempt == _MAX_RETRIES - 1:
                    logger.error(
                        f"数据库连接错误，重试{_MAX_RETRIES}次失败: {e}", LOG_COMMAND
                    )
                    raise
                delay = _BASE_DELAY * (2**attempt)
                logger.warning(
                    f"数据库连接错误，正在重试 ({attempt + 1}/{_MAX_RETRIES})，"
                    f"延迟{delay:.2f}秒: {e}",
                    LOG_COMMAND,
                )
                await asyncio.sleep(delay)
        # 理论不可达：最后一次重试失败时已在上方抛出，兜底防止隐式返回 None
        raise RuntimeError(f"查询重试流程异常退出: {self.model_class.__name__}")

    # ========== 查询执行方法 ==========

    async def first(self) -> Any | None:
        """获取查询结果的第一条记录

        如需"不存在则创建"，请使用 ``Model.get_or_create``，
        此处不再自动创建（避免忽略链上 args/exclude 条件产生错误数据）。

        返回:
            第一条记录，不存在时返回 None
        """
        stmt = self._build_base_query().limit(1)
        fetch = "first_row" if self._returns_rows() else "first"
        return await self._execute_query(stmt, fetch)

    async def one(self) -> Any:
        """获取唯一记录，不存在或存在多条时抛出异常

        与 ``first`` 不同，此方法要求结果精确为一条，适用于主键或唯一约束查询。

        返回:
            唯一匹配的记录

        抛出:
            sqlalchemy.exc.NoResultFound: 未找到记录
            sqlalchemy.exc.MultipleResultsFound: 找到多条记录
        """
        stmt = self._build_base_query().limit(2)
        fetch = "one_row" if self._returns_rows() else "one"
        return await self._execute_query(stmt, fetch)

    async def one_or_none(self) -> Any | None:
        """获取唯一记录或None，存在多条时抛出异常

        返回:
            唯一匹配的记录，未找到返回None

        抛出:
            sqlalchemy.exc.MultipleResultsFound: 找到多条记录
        """
        stmt = self._build_base_query().limit(2)
        fetch = "one_row_or_none" if self._returns_rows() else "one_or_none"
        return await self._execute_query(stmt, fetch)

    async def earliest(self, field: str | None = None) -> Any | None:
        """按指定字段升序取第一条记录

        参数:
            field: 排序字段，未指定时回退到 "id"
        """
        return await self.order_by(field or "id").first()

    async def latest(self, field: str | None = None) -> Any | None:
        """按指定字段降序取第一条记录

        参数:
            field: 排序字段，未指定时回退到 "id"
        """
        return await self.order_by(f"-{field or 'id'}").first()

    async def all(self) -> list[Any]:
        """获取查询结果的所有记录

        返回:
            所有记录的列表
        """
        stmt = self._build_base_query()
        fetch = "fetchall" if self._returns_rows() else "all"
        return await self._execute_query(stmt, fetch)

    async def count(self, include_deleted: bool = False) -> int:
        """获取查询结果的记录数

        参数:
            include_deleted: 是否包含软删除记录（仅当模型含 deleted_at 字段时有效），
                             默认 False 沿用软删除过滤。仅影响本次调用，
                             不会改变 wrapper 的后续查询状态。

        返回:
            记录数量
        """
        prev_with_deleted = self._with_deleted
        if include_deleted and hasattr(self.model_class, "deleted_at"):
            self._with_deleted = True
        try:
            base = self._apply_filters(select(self.model_class))
        finally:
            self._with_deleted = prev_with_deleted
        stmt = select(func.count()).select_from(base.subquery())
        return await self._execute_query(stmt, "count")

    async def group_count(
        self,
        group_column: str | Any,
        count_column: str | Any | None = None,
        desc: bool = True,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[tuple[Any, int]]:
        """按指定列分组统计记录数量

        参数:
            group_column: 分组列名或列对象
            count_column: 计数列名或列对象，为None时统计全部记录
            desc: 是否按计数降序排列，默认True
            limit: 返回前N条记录，为None时返回全部
            offset: 跳过前N条记录，与limit配合实现分页

        返回:
            list[tuple[Any, int]]: [(分组值, 计数), ...] 按计数排序
        """
        group_col = DbUtils.get_column(self.model_class, group_column)
        if count_column is not None:
            count_expr = func.count(
                DbUtils.get_column(self.model_class, count_column)
            ).label("count")
        else:
            count_expr = func.count().label("count")
        stmt = select(group_col, count_expr)
        stmt = self._apply_filters(stmt)
        stmt = stmt.group_by(group_col)
        stmt = stmt.order_by(count_expr.desc() if desc else count_expr.asc())
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        rows = await self._execute_query(stmt, "fetchall")
        return [(row[0], row[1]) for row in rows]

    async def group_dict(
        self,
        key_column: str | Any,
        value_column: str | Any,
        limit_per_key: int | None = None,
    ) -> dict[Any, list[Any]]:
        """按 key 列分组，返回 {key: [value, ...]} 映射

        参数:
            key_column: 作为字典键的列名或列对象
            value_column: 作为字典值的列名或列对象
            limit_per_key: 每个分组最多保留的值数量，为None时不限制

        返回:
            dict[Any, list[Any]]: 分组映射字典
        """
        key_col = DbUtils.get_column(self.model_class, key_column)
        val_col = DbUtils.get_column(self.model_class, value_column)
        stmt = self._build_base_query(select(key_col, val_col))
        rows = await self._execute_query(stmt, "fetchall")
        result: dict[Any, list[Any]] = {}
        for row in rows:
            values = result.setdefault(row[0], [])
            if limit_per_key is None or len(values) < limit_per_key:
                values.append(row[1])
        return result

    async def exists(self) -> bool:
        """检查是否存在符合条件的记录

        返回:
            bool: 如果存在记录返回True
        """
        stmt = self._build_base_query()
        return await self._execute_query(select(stmt.exists()), "scalar")

    async def get(self, pk: Any) -> Any | None:
        """根据主键获取单个记录

        参数:
            pk: 主键值

        返回:
            单个记录对象，如果不存在则返回None

        抛出:
            ValueError: 模型无主键或为复合主键
        """
        pk_names = DbUtils.get_primary_key_names(self.model_class)
        if not pk_names:
            raise ValueError(f"模型 {self.model_class.__name__} 没有主键")
        if len(pk_names) > 1:
            raise ValueError(
                f"模型 {self.model_class.__name__} 为复合主键，"
                f"不支持 get(pk)，请使用 filter"
            )
        stmt = self._build_base_query()
        stmt = stmt.where(getattr(self.model_class, pk_names[0]) == pk)
        return await self._execute_query(stmt.limit(1), "first")

    async def find_by(self, skip_none: bool = False, **kwargs: Any) -> Any | None:
        """根据指定条件查找单个记录

        参数:
            skip_none: 为True时忽略值为None的kwargs条件
            **kwargs: 查询条件
        """
        return await self.filter(skip_none=skip_none, **kwargs).first()

    async def find_all(self, skip_none: bool = False, **kwargs: Any) -> list[Any]:
        """根据指定条件查找所有记录

        参数:
            skip_none: 为True时忽略值为None的kwargs条件
            **kwargs: 查询条件
        """
        return await self.filter(skip_none=skip_none, **kwargs).all()

    async def paginate(
        self,
        page: int = 1,
        per_page: int = 20,
        max_per_page: int | None = None,
    ) -> dict[str, Any]:
        """分页查询

        参数:
            page: 页码，从1开始
            per_page: 每页记录数
            max_per_page: 每页记录数上限，防止传入过大值导致性能问题

        返回:
            dict: 包含分页信息的字典
        """
        if max_per_page is not None:
            per_page = min(per_page, max_per_page)
        total = await self.count()
        self._limit = per_page
        self._offset = (page - 1) * per_page
        items = await self.all()
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        }

    async def aggregate(self, *aggregations: Any, **named_aggregations: Any) -> Any:
        """聚合查询

        参数:
            *aggregations: 聚合函数列表
            **named_aggregations: 命名聚合，如 total=func.count('*')

        返回:
            命名聚合时返回 dict，否则返回第一行 Row
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
        """获取单个列的值列表"""
        col = DbUtils.get_column(self.model_class, column)
        stmt = self._build_base_query(select(col))
        result = await self._execute_query(stmt, "fetchall")
        return [row[0] for row in result]

    async def values_list(
        self, *fields: str, flat: bool = False
    ) -> list[Any] | list[tuple]:
        """获取指定列的值列表

        参数:
            *fields: 列名列表
            flat: 如果为True且只指定一个字段，则返回扁平列表
        """
        if not fields:
            stmt = self._build_base_query()
        else:
            cols = [DbUtils.get_column(self.model_class, f) for f in fields]
            stmt = self._build_base_query(select(*cols))
        result = await self._execute_query(stmt, "fetchall")
        if flat and len(fields) == 1:
            return [row[0] for row in result]
        return result

    async def values_dict(self, *fields: str) -> list[dict[str, Any]]:
        """直接从数据库行返回字典列表，比 to_dict 更高效

        ``to_dict`` 需先加载完整 ORM 对象再逐字段取值，此方法直接查询指定列
        并从行映射构建字典，减少对象实例化开销。

        参数:
            *fields: 要查询的字段名，为空时返回所有列

        返回:
            list[dict[str, Any]]: 字段名到值的字典列表
        """
        if fields:
            cols = [DbUtils.get_column(self.model_class, f) for f in fields]
            stmt = self._build_base_query(select(*cols))
        else:
            stmt = self._build_base_query()
        rows = await self._execute_query(stmt, "mappings")
        return [dict(row) for row in rows]

    async def explain(self, analyze: bool = False) -> list[Any]:
        """获取查询执行计划

        参数:
            analyze: 为True时执行 EXPLAIN ANALYZE，实际运行查询并返回
                     包含执行时间的计划，适合性能调优；默认False仅分析
        """
        stmt = self._build_base_query()
        prefix = "EXPLAIN ANALYZE " if analyze else "EXPLAIN "
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        async with self.model_class.get_session(db_name=self._db_name) as session:
            result = await session.execute(text(prefix + compiled))
            return result.fetchall()

    async def raw(self, sql: str, params: dict[str, Any] | None = None) -> Any:
        """执行原始SQL语句

        警告:
            此方法允许执行任意SQL语句，存在SQL注入风险。
            请确保所有用户输入通过 params 参数传递。

        参数:
            sql: 原始SQL语句，使用 :param 形式的命名参数
            params: SQL参数字典
        """
        async with self.model_class.get_session(db_name=self._db_name) as session:
            return await session.execute(text(sql), params or {})

    def _spawn(self) -> "QueryWrapper":
        """基于当前查询条件创建独立的 wrapper，不共享可变状态

        供 ``find_in_batches`` 等需要重建查询链的方法复用，
        完整保留 exclude 条件、软删除状态与目标数据库配置。
        """
        spawn = self.model_class.filter(*self.args, **self.kwargs)
        spawn._exclude_args = self._exclude_args
        spawn._exclude_kwargs = dict(self._exclude_kwargs)
        spawn._with_deleted = self._with_deleted
        spawn._db_name = self._db_name
        return spawn

    async def find_in_batches(
        self, batch_size: int = 1000
    ) -> AsyncGenerator[list[Any]]:
        """分批处理大量数据

        优先使用基于主键的 keyset pagination（避免深分页性能问题），
        无主键时回退到 OFFSET 分页。不修改 QueryWrapper 自身状态。

        参数:
            batch_size: 每批处理的记录数

        返回:
            AsyncGenerator: 异步生成器，每次产生一批记录
        """
        pk_names = DbUtils.get_primary_key_names(self.model_class)
        if not pk_names:
            # 无主键，回退到 OFFSET 分页
            offset = 0
            while True:
                batch = await self._spawn().limit(batch_size).offset(offset).all()
                if not batch:
                    break
                yield batch
                offset += batch_size
                if len(batch) < batch_size:
                    break
            return

        # 基于主键的 keyset pagination
        pk_col = DbUtils.get_column(self.model_class, pk_names[0])
        last_pk = None
        while True:
            query = self._spawn()
            if last_pk is not None:
                query = query.filter(pk_col > last_pk)
            batch = await query.order_by(pk_col.asc()).limit(batch_size).all()
            if not batch:
                break
            yield batch
            if len(batch) < batch_size:
                break
            last_pk = getattr(batch[-1], pk_names[0])

    async def iterator(self, chunk_size: int = 1000) -> AsyncGenerator[Any]:
        """流式迭代查询结果

        参数:
            chunk_size: 每次预读取的记录数

        返回:
            AsyncGenerator: 每次产生一条记录
        """
        stmt = self._build_base_query()
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
        self, id_list: list[Any], field_name: str = "id"
    ) -> dict[Any, Any]:
        """批量按字段值查询，返回字段值到实例的映射"""
        if not id_list:
            return {}
        col = DbUtils.get_column(self.model_class, field_name)
        records = await self.filter(col.in_(id_list)).all()
        return {getattr(r, field_name): r for r in records}

    async def get_or_create(
        self, defaults: dict[str, Any] | None = None, **kwargs: Any
    ) -> tuple[Any, bool]:
        """获取或创建记录"""
        return await self.model_class.get_or_create(
            defaults=defaults, db_name=self._db_name, **kwargs
        )

    async def update_or_create(
        self, defaults: dict[str, Any] | None = None, **kwargs: Any
    ) -> tuple[Any, bool]:
        """更新或创建记录"""
        return await self.model_class.update_or_create(
            defaults=defaults, db_name=self._db_name, **kwargs
        )

    async def _aggregate_column(
        self, column: str | Any, func_type: Any, distinct: bool = False
    ) -> Any:
        """聚合函数的通用方法

        参数:
            column: 列名或列对象
            func_type: 聚合函数，如 func.sum / func.avg
            distinct: 是否对列值去重后再聚合
        """
        col = DbUtils.get_column(self.model_class, column)
        expr = func_type(col.distinct() if distinct else col)
        stmt = self._build_base_query(select(expr))
        return await self._execute_query(stmt, "scalar")

    async def min(self, column: str | Any) -> Any:
        """获取指定列的最小值"""
        return await self._aggregate_column(column, func.min)

    async def max(self, column: str | Any) -> Any:
        """获取指定列的最大值"""
        return await self._aggregate_column(column, func.max)

    async def avg(self, column: str | Any, distinct: bool = False) -> float | None:
        """获取指定列的平均值

        参数:
            column: 列名或列对象
            distinct: 为True时计算 DISTINCT 平均值（去重后求均值）
        """
        return await self._aggregate_column(column, func.avg, distinct)

    async def sum(self, column: str | Any, distinct: bool = False) -> Any:
        """获取指定列的总和

        参数:
            column: 列名或列对象
            distinct: 为True时计算 DISTINCT 总和（去重后求和）
        """
        return await self._aggregate_column(column, func.sum, distinct)

    # ========== 修改操作方法 ==========

    async def update(self, **values: Any) -> int:
        """批量更新

        参数:
            **values: 要更新的字段和值

        返回:
            int: 受影响的行数
        """
        async with self.model_class.get_session(db_name=self._db_name) as session:
            stmt = self._apply_filters(update(self.model_class)).values(**values)
            result = await session.execute(stmt)
            await self._invalidate_write_cache()
            return result.rowcount

    async def delete(self) -> int:
        """批量删除

        返回:
            int: 受影响的行数
        """
        async with self.model_class.get_session(db_name=self._db_name) as session:
            stmt = self._apply_filters(delete(self.model_class))
            result = await session.execute(stmt)
            await self._invalidate_write_cache()
            return result.rowcount

    @staticmethod
    def _build_mapping(obj: Any, fields: list[str] | None = None) -> dict:
        """构建对象映射字典"""
        if fields is None:
            return {col.name: getattr(obj, col.name) for col in obj.__table__.columns}
        mapping = {f: getattr(obj, f) for f in fields if hasattr(obj, f)}
        for pk in DbUtils.get_primary_key_names(obj.__class__):
            if hasattr(obj, pk):
                mapping[pk] = getattr(obj, pk)
        return mapping

    @staticmethod
    def _iter_batches(items: list[Any], batch_size: int | None) -> list[list[Any]]:
        """将列表切分为批次

        参数:
            items: 待切分列表
            batch_size: 批次大小，None或非正数时返回单批

        返回:
            list[list[Any]]: 批次列表
        """
        if not items:
            return []
        if not batch_size or batch_size <= 0:
            return [items]
        return [list(batch) for batch in itertools.batched(items, batch_size)]

    async def bulk_create(
        self,
        objects: list[Any],
        batch_size: int | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
        refresh: bool = False,
    ) -> list[Any]:
        """批量创建记录

        参数:
            objects: 要创建的对象列表
            batch_size: 批量大小，用于分批创建
            progress_callback: 进度回调函数 (当前数量, 总数量)
            refresh: 是否刷新对象以获取数据库生成的默认值（如自增ID）。
                     flush 后自增主键已自动填充，仅在需要其他服务端默认值时开启，
                     开启后会对每个对象执行单独的 SELECT，大批量时性能较差。

        返回:
            list: 创建后的对象列表
        """
        if not objects:
            return []
        total = len(objects)
        processed = 0
        async with self.model_class.get_session(db_name=self._db_name) as session:
            for batch in self._iter_batches(objects, batch_size):
                session.add_all(batch)
                await session.flush()
                processed += len(batch)
                if progress_callback:
                    progress_callback(processed, total)
            if refresh:
                for obj in objects:
                    await session.refresh(obj)
            await self._invalidate_write_cache()
            return objects

    async def bulk_update(
        self,
        objects: list[Any],
        fields: list[str] | None = None,
        batch_size: int | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> int:
        """批量更新多个记录"""
        if not objects:
            return 0
        total = len(objects)
        updated = 0
        async with self.model_class.get_session(db_name=self._db_name) as session:
            for batch in self._iter_batches(objects, batch_size):
                mappings = [self._build_mapping(o, fields) for o in batch]
                await session.run_sync(
                    lambda s: s.bulk_update_mappings(self.model_class, mappings)
                )
                updated += len(batch)
                if progress_callback:
                    progress_callback(updated, total)
            await self._invalidate_write_cache()
            return updated

    async def bulk_delete(
        self,
        objects: list[Any],
        batch_size: int | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> int:
        """批量删除多个记录"""
        if not objects:
            return 0
        total = len(objects)
        deleted = 0
        async with self.model_class.get_session(db_name=self._db_name) as session:
            for batch in self._iter_batches(objects, batch_size):
                for obj in batch:
                    await session.delete(obj)
                    deleted += 1
                await session.flush()
                if progress_callback:
                    progress_callback(deleted, total)
            await self._invalidate_write_cache()
            return deleted

    async def _atomic_update(self, column: str | Any, amount: int) -> int:
        """原子性更新字段值（增减）"""
        col = DbUtils.get_column(self.model_class, column)
        async with self.model_class.get_session(db_name=self._db_name) as session:
            stmt = self._apply_filters(update(self.model_class))
            stmt = stmt.values({col: col + amount})
            result = await session.execute(stmt)
            await self._invalidate_write_cache()
            return result.rowcount

    async def increment(self, column: str | Any, amount: int = 1) -> int:
        """原子性增加字段值"""
        return await self._atomic_update(column, amount)

    async def decrement(self, column: str | Any, amount: int = 1) -> int:
        """原子性减少字段值"""
        return await self._atomic_update(column, -amount)

    async def soft_delete(self) -> int:
        """软删除符合条件的记录，设置 deleted_at 为当前时间"""
        if not hasattr(self.model_class, "deleted_at"):
            raise AttributeError(
                f"模型 {self.model_class.__name__} 没有 deleted_at 字段，无法执行软删除"
            )
        async with self.model_class.get_session(db_name=self._db_name) as session:
            stmt = self._apply_filters(update(self.model_class))
            stmt = stmt.values(deleted_at=datetime.now())
            result = await session.execute(stmt)
            await self._invalidate_write_cache()
            return result.rowcount

    async def restore(self) -> int:
        """恢复软删除的记录，将 deleted_at 设为 None"""
        if not hasattr(self.model_class, "deleted_at"):
            raise AttributeError(
                f"模型 {self.model_class.__name__} 没有 deleted_at 字段，无法执行恢复"
            )
        prev_with_deleted = self._with_deleted
        self._with_deleted = True
        try:
            async with self.model_class.get_session(db_name=self._db_name) as session:
                stmt = self._apply_filters(update(self.model_class))
                stmt = stmt.values(deleted_at=None)
                result = await session.execute(stmt)
        finally:
            self._with_deleted = prev_with_deleted
        await self._invalidate_write_cache()
        return result.rowcount
