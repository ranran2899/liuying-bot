"""查询包装器模块，提供链式调用的查询接口

QueryWrapper 采用 Mixin 模式组合多个功能域，实现关注点分离：
- BaseQueryBuilder: 基础查询结构（排序、分页、连接、分组）
- ConditionQueryBuilder: 条件过滤（等值、范围、模糊、日期等条件）
- QueryExecutionBuilder: 查询执行和聚合（first/all/count/paginate等）
- UpdateDeleteBuilder: 数据修改操作（update/delete/bulk操作）
"""

import asyncio
import hashlib
import time
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.exc import (
    DBAPIError,
    DisconnectionError,
    InterfaceError,
    OperationalError,
)
from sqlalchemy.orm import defer, joinedload, selectinload
from sqlalchemy.sql.selectable import Select

from liuying.services.cache import Cache
from liuying.utils.log import logger

from ..config import LOG_COMMAND, QUERY_TIMEOUT_SECONDS, SLOW_QUERY_THRESHOLD
from .base import BaseQueryBuilder
from .condition import ConditionQueryBuilder
from .execution import QueryExecutionBuilder
from .modify import UpdateDeleteBuilder

if TYPE_CHECKING:
    from ..base_model import Model

T = TypeVar("T", bound="Model")

max_retries = QUERY_TIMEOUT_SECONDS.max_retries
base_delay = QUERY_TIMEOUT_SECONDS.base_delay

_query_cache = Cache("LIUYING_DB_QUERY")
"""数据库查询结果缓存实例（使用原始键 raw_get/raw_set 操作）"""

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

_RESULT_HANDLERS = {
    "first": lambda r: r.scalars().first(),
    "all": lambda r: r.scalars().all(),
    "scalar": lambda r: r.scalar(),
    "count": lambda r: r.scalar(),
    "rowcount": lambda r: r.rowcount,
    "first_row": lambda r: r.first(),
    "fetchall": lambda r: r.fetchall(),
}


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


class QueryWrapper(
    Generic[T],
    BaseQueryBuilder,
    ConditionQueryBuilder,
    QueryExecutionBuilder,
    UpdateDeleteBuilder,
):
    """查询包装器类，提供链式调用的查询接口

    类型参数:
        T: 模型类型，必须继承自 Model 基类

    使用示例:
        # 链式调用示例
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
        "_for_update_options",
        "_group_by",
        "_having",
        "_join_conditions",
        "_limit",
        "_load_relationships",
        "_lock_mode",
        "_offset",
        "_order_by",
        "_values",
        "_with_deleted",
        "args",
        "kwargs",
        "model_class",
    )

    def __init__(self, model_class: type[T], *args, **kwargs):
        """初始化查询包装器

        参数:
            model_class: 模型类
            *args: 查询条件
            **kwargs: 查询条件
        """
        self.model_class = model_class
        self.args = args
        self.kwargs = kwargs
        self._limit = None
        self._offset = None
        self._order_by = None
        self._distinct = False
        self._join_conditions = []
        self._group_by = None
        self._having = None
        self._values = None
        self._lock_mode = None
        self._db_name = "default"
        self._with_deleted = False
        self._cache_key = None
        self._cache_ttl = None
        self._annotations = None
        self._deferred_fields = []
        self._for_update_options = None
        self._load_relationships = []

    @property
    def _cache_enabled(self) -> bool:
        """缓存是否启用"""
        return self._cache_ttl is not None and self._cache_ttl > 0

    def _apply_relationship_load_options(self, stmt: Select) -> Select:
        """应用关联关系预加载选项

        参数:
            stmt: 查询语句

        返回:
            Select: 应用预加载选项后的查询语句
        """
        for field in getattr(self, "_deferred_fields", []):
            stmt = stmt.options(defer(field))

        for relationship, options in self._load_relationships:
            strategy = options.get("strategy", "selectin")
            if isinstance(relationship, str):
                relationship_path = relationship.split(".")
                current_attr = getattr(self.model_class, relationship_path[0])
                for rel_part in relationship_path[1:]:
                    current_attr = getattr(
                        current_attr.property.mapper.class_, rel_part
                    )
                relationship = current_attr

            match strategy:
                case "joined":
                    stmt = stmt.options(joinedload(relationship))
                case _:
                    stmt = stmt.options(selectinload(relationship))
        return stmt

    def _apply_order_limit(self, stmt: Select) -> Select:
        """应用排序和限制条件

        参数:
            stmt: 查询语句

        返回:
            Select: 应用排序和限制后的查询语句
        """
        if self._group_by:
            stmt = stmt.group_by(*self._group_by)

        if self._having:
            stmt = stmt.having(self._having)

        if self._order_by:
            stmt = stmt.order_by(*self._order_by)

        if self._distinct:
            stmt = stmt.distinct()

        if for_update_options := getattr(self, "_for_update_options", None):
            stmt = stmt.with_for_update(**for_update_options)
        elif self._lock_mode:
            stmt = stmt.with_for_update(read=self._lock_mode == "FOR SHARE")

        return stmt

    def _build_base_query(self, stmt: Select | None = None) -> Select:
        """构建基础查询语句

        参数:
            stmt: 基础查询语句，如果为None则创建新的查询语句

        返回:
            Select: 构建好的查询语句
        """
        if stmt is None:
            if self._values:
                stmt = select(*self._values)
            elif annotations := getattr(self, "_annotations", None):
                stmt = select(self.model_class, *annotations.values())
            else:
                stmt = select(self.model_class)

        stmt = self._apply_filters(stmt)
        stmt = self._apply_order_limit(stmt)
        stmt = self._apply_relationship_load_options(stmt)

        return stmt

    async def _execute_query(self, stmt: Select, fetch_type: str = "all") -> Any:
        """执行查询并返回结果，包含智能重试机制

        参数:
            stmt: 查询语句
            fetch_type: 获取结果类型，
                       支持 first/all/scalar/count/rowcount/first_row/fetchall

        返回:
            Any: 查询结果

        抛出:
            ValueError: 不支持的fetch_type
            OperationalError: 数据库操作错误（重试后）
            DisconnectionError: 数据库断开连接（重试后）
        """
        if fetch_type not in _RESULT_HANDLERS:
            raise ValueError(f"不支持的fetch_type: {fetch_type}")

        cache_key = self._cache_key
        if cache_key is None and self._cache_enabled:
            stmt_hash = hashlib.md5(str(stmt).encode("utf-8")).hexdigest()
            cache_key = (
                f"{self._db_name}:{self.model_class.__name__}:"
                f"{fetch_type}:{stmt_hash}"
            )

        if self._cache_enabled and cache_key:
            try:
                cached_result = await _query_cache.raw_get(cache_key)
                if cached_result is not None:
                    return cached_result
            except Exception as e:
                logger.warning(f"缓存读取失败，降级为数据库查询: {e}", LOG_COMMAND)

        for attempt in range(max_retries):
            try:
                async with self.model_class.get_session(
                    db_name=self._db_name
                ) as session:
                    final_stmt = stmt
                    if self._limit:
                        final_stmt = final_stmt.limit(self._limit)
                    if self._offset:
                        final_stmt = final_stmt.offset(self._offset)

                    start_time = time.perf_counter()
                    result = await session.execute(final_stmt)
                    elapsed = time.perf_counter() - start_time

                    if elapsed > SLOW_QUERY_THRESHOLD:
                        logger.warning(
                            f"慢查询检测 [{self._db_name}] "
                            f"{self.model_class.__name__}.{fetch_type} "
                            f"耗时: {elapsed:.3f}s, "
                            f"阈值: {SLOW_QUERY_THRESHOLD}s",
                            LOG_COMMAND,
                        )

                    query_result = _RESULT_HANDLERS[fetch_type](result)

                    if self._cache_enabled and cache_key:
                        try:
                            await _query_cache.raw_set(
                                cache_key, query_result, expire=self._cache_ttl
                            )
                        except Exception as e:
                            logger.warning(f"缓存写入失败: {e}", LOG_COMMAND)

                    return query_result

            except _RETRYABLE_ERRORS as e:
                if not _is_retryable_error(e):
                    raise

                if attempt == max_retries - 1:
                    logger.error(
                        f"数据库连接错误，重试{max_retries}次失败: {e}",
                        LOG_COMMAND,
                    )
                    raise

                delay = base_delay * (2**attempt)
                logger.warning(
                    f"数据库连接错误，正在重试 ({attempt + 1}/{max_retries})，"
                    f"延迟{delay:.2f}秒: {e}",
                    LOG_COMMAND,
                )
                await asyncio.sleep(delay)
                continue

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

        参数:
            key: 缓存键，默认为None自动生成
            ttl: 缓存过期时间（秒），默认为300秒

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        self._cache_key = key
        self._cache_ttl = ttl
        return self

    def preload(self, *relationships, **options) -> "QueryWrapper[T]":
        """预加载关联关系

        参数:
            *relationships: 要预加载的关系名称
            **options: 预加载选项

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        for relationship in relationships:
            self._load_relationships.append((relationship, options))
        return self

    def select_related(self, *relationships) -> "QueryWrapper[T]":
        """使用joinedload策略预加载（适合一对一关系）

        参数:
            *relationships: 要预加载的关系名称

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        for relationship in relationships:
            self._load_relationships.append((relationship, {"strategy": "joined"}))
        return self

    def prefetch_related(self, *relationships) -> "QueryWrapper[T]":
        """使用selectinload策略预加载（适合一对多关系）

        参数:
            *relationships: 要预加载的关系名称

        返回:
            QueryWrapper[T]: 返回自身以支持链式调用
        """
        for relationship in relationships:
            self._load_relationships.append((relationship, {"strategy": "selectin"}))
        return self
