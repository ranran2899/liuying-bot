"""数据库模型基类模块

提供 SQLAlchemy 2.0 声明式基类 ``Base`` 与增强的 ORM 基类 ``Model``。
``Model`` 封装了缓存集成、异步锁机制与完整的 CRUD 接口，外部模型
统一继承此类获得数据库操作能力。
"""

import asyncio
from collections.abc import Iterable
import contextlib
from typing import Any, ClassVar, Self
import weakref

from sqlalchemy import and_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from liuying.services.cache import Cache, CacheRoot
from liuying.services.cache.config import COMPOSITE_KEY_SEPARATOR
from liuying.utils.enum import DbLockType
from liuying.utils.log import logger

from .config import LOG_COMMAND, db_model
from .query import QueryWrapper, build_filter_statement, query_cache_namespace
from .session import nested_transaction, session_manager
from .utils import DbUtils


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 声明式基类

    所有数据库模型都应继承此类以获得声明式映射功能。
    """


class Model(Base):
    """增强的 ORM 基类，基于 SQLAlchemy 2.0 异步

    提供缓存集成、异步锁机制与完整的 CRUD 接口。
    所有业务模型应继承此类。
    """

    __abstract__ = True

    _locks: ClassVar[dict[str, asyncio.Lock]] = {}
    _current_locks: ClassVar[dict[int, DbLockType]] = {}
    _task_refs: ClassVar[weakref.WeakSet[asyncio.Task]] = weakref.WeakSet()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if func := getattr(cls, "_run_script", None):
            db_model.script_methods.append((cls.__module__, func))
        cls._register_cache_type()

    @classmethod
    def _register_cache_type(cls) -> None:
        """自动注册缓存类型到 CacheRoot

        根据 cache_key_field 类型决定注册方式：
        1. "all"：整表缓存，以 list[cls] 作为结果类型注册
        2. tuple：复合键，按字段顺序自动生成 key_format 注册
        3. str：单键，直接注册（DataAccess 不经 Cache.__init__，必须主动注册）

        已注册的 cache_type 跳过，避免子类覆盖既有配置。
        共享 cache_type 的非主模型不应声明 cache_type，以免抢占注册。
        """
        cache_type = getattr(cls, "cache_type", None)
        if cache_type is None or CacheRoot.is_valid(cache_type):
            return
        key_field = getattr(cls, "cache_key_field", "id")
        match key_field:
            case "all":
                CacheRoot.register(cache_type, list[cls])
            case tuple(fields):
                key_format = COMPOSITE_KEY_SEPARATOR.join(
                    f"{{{f}}}" for f in fields
                )
                CacheRoot.register(cache_type, cls, key_format=key_format)
            case str():
                CacheRoot.register(cache_type, cls)

    @classmethod
    def filter(cls, *args, skip_none: bool = False, **kwargs) -> QueryWrapper:
        """便捷的过滤查询方法，自动处理会话管理

        支持 SQLAlchemy 风格查询和 Django 风格查询。

        参数:
            *args: SQLAlchemy 过滤表达式
            skip_none: 为True时忽略值为None的kwargs条件
            **kwargs: 查询条件，支持以下两种风格:
                - SQLAlchemy风格: name="test" (精确匹配)
                - Django风格: name__contains="test" (包含匹配)

        返回:
            QueryWrapper: 查询包装器

        使用示例:
            Model.filter(name="test", status=1)
            Model.filter(name__contains="test", status__gt=0)
            Model.filter(skip_none=True, name=None, status=1)  # 忽略name条件
        """
        return QueryWrapper(cls, *args, skip_none=skip_none, **kwargs)

    @classmethod
    def get_cache_type(cls) -> str | None:
        """获取缓存类型"""
        return getattr(cls, "cache_type", None)

    @classmethod
    def get_cache_key_field(cls) -> str | tuple[str, ...]:
        """获取缓存键字段"""
        return getattr(cls, "cache_key_field", "id")

    @classmethod
    def get_cache_key(cls, instance) -> str | None:
        """获取缓存键

        参数:
            instance: 模型实例

        返回:
            str | None: 缓存键
        """
        key_field = cls.get_cache_key_field()
        match key_field:
            case tuple(fields):
                parts = [
                    str(v) if (v := getattr(instance, f, None)) is not None else ""
                    for f in fields
                ]
                return COMPOSITE_KEY_SEPARATOR.join(parts) if parts else None
            case _:
                value = getattr(instance, key_field, None)
                return str(value) if value is not None else None

    @classmethod
    def _get_lock(cls, lock_type: DbLockType) -> asyncio.Lock | None:
        """获取指定类型的异步锁

        参数:
            lock_type: 锁类型

        返回:
            asyncio.Lock | None: 异步锁，未启用返回 None
        """
        enable_lock = getattr(cls, "enable_lock", None)
        if not enable_lock or lock_type not in enable_lock:
            return None
        lock_key = f"{cls.__name__}:{lock_type}"
        if lock_key not in cls._locks:
            cls._locks[lock_key] = asyncio.Lock()
        return cls._locks[lock_key]

    @classmethod
    def _require_lock(cls, lock_type: DbLockType) -> bool:
        """检查当前协程是否需要加锁"""
        task = asyncio.current_task()
        if task is None:
            return True
        return cls._current_locks.get(id(task)) != lock_type

    @classmethod
    def _cleanup_lock_record(cls, task_id: int):
        """清理锁记录，防止内存泄漏"""
        cls._current_locks.pop(task_id, None)

    @classmethod
    @contextlib.asynccontextmanager
    async def _lock_context(cls, lock_type: DbLockType):
        """带重入检查的锁上下文，使用 asyncio.Lock 替代 Semaphore"""
        task = asyncio.current_task()
        task_id = id(task) if task else 0
        need_lock = cls._require_lock(lock_type)
        if need_lock and (lock := cls._get_lock(lock_type)):
            cls._current_locks[task_id] = lock_type
            if task:
                cls._task_refs.add(task)
            try:
                async with lock:
                    yield
            finally:
                cls._cleanup_lock_record(task_id)
        else:
            yield

    @classmethod
    @contextlib.asynccontextmanager
    async def get_session(cls, db_name: str = "default"):
        """获取数据库会话的上下文管理器

        参数:
            db_name: 数据库名称
        """
        async with cls._managed_session(db_name=db_name) as session:
            yield session

    @classmethod
    @contextlib.asynccontextmanager
    async def _managed_session(
        cls, session: AsyncSession | None = None, db_name: str = "default"
    ):
        """管理数据库会话，如果提供了 session 则使用，否则创建新的

        参数:
            session: 可选的数据库会话
            db_name: 数据库名称
        """
        if session is not None:
            yield session
            return
        async with session_manager.get_session(db_name) as sess:
            yield sess

    @classmethod
    async def _handle_integrity_error(
        cls, session: AsyncSession, kwargs: dict
    ) -> tuple[Self | None, bool]:
        """处理完整性错误，用于 get_or_create 和 update_or_create

        插入操作已在 nested_transaction（savepoint）中执行，
        IntegrityError 仅回滚保存点，外部事务仍然可用，可直接查询。

        参数:
            session: 数据库会话
            kwargs: 查询条件

        返回:
            tuple[Self | None, bool]: 模型实例和是否为新创建
        """
        stmt = build_filter_statement(cls, **kwargs)
        result = await session.execute(stmt)
        return result.scalars().first(), False

    @classmethod
    async def _invalidate_cache(cls, instance):
        """使缓存失效

        统一的缓存失效入口，写操作（create/update/delete）后调用。
        当模型声明了 ``cache_type`` 时，按 ``cache_key_field`` 删除对应缓存键；
        同时按模型命名空间失效该模型的查询结果缓存（``QueryWrapper`` 查询缓存）。

        参数:
            instance: 模型实例
        """
        if cache_type := cls.get_cache_type():
            cache_key = cls.get_cache_key(instance)
            if cache_key is not None:
                cache = Cache(cache_type, result_type=cls)
                await cache.delete(cache_key)
        # 按模型命名空间清空查询缓存，避免读到已删除/未变更的数据
        try:
            await CacheRoot.invalidate_namespace(query_cache_namespace(cls))
        except Exception as e:
            logger.debug(f"清除查询缓存失败: {e}", LOG_COMMAND)

    @classmethod
    async def create(
        cls,
        session: AsyncSession | None = None,
        db_name: str = "default",
        **kwargs: Any,
    ) -> Self:
        """创建数据（使用 CREATE 锁）

        参数:
            session: 可选的数据库会话
            db_name: 数据库名称
            **kwargs: 模型字段参数

        返回:
            Self: 创建的模型实例

        抛出:
            IntegrityError: 违反数据库约束（如唯一约束）
            OperationalError: 数据库操作错误
        """
        async with cls._managed_session(session, db_name) as sess:
            async with cls._lock_context(DbLockType.CREATE):
                instance = cls(**kwargs)
                sess.add(instance)
                await sess.flush()
                await sess.refresh(instance)
                await cls._invalidate_cache(instance)
                return instance

    @classmethod
    async def get_or_create(
        cls,
        session: AsyncSession | None = None,
        defaults: dict | None = None,
        db_name: str = "default",
        **kwargs: Any,
    ) -> tuple[Self, bool]:
        """获取或创建数据（无锁版本，依赖数据库约束）

        参数:
            session: 可选的数据库会话
            defaults: 默认值字典
            db_name: 数据库名称
            **kwargs: 查询条件

        返回:
            tuple[Self, bool]: 模型实例和是否为新创建
        """
        async with cls._managed_session(session, db_name) as sess:
            stmt = build_filter_statement(cls, **kwargs)
            result = await sess.execute(stmt)
            instance = result.scalars().first()
            if instance:
                return instance, False
            try:
                async with nested_transaction(sess):
                    instance = cls(**kwargs, **(defaults or {}))
                    sess.add(instance)
                    await sess.flush()
                    await sess.refresh(instance)
                await cls._invalidate_cache(instance)
                return instance, True
            except IntegrityError:
                return await cls._handle_integrity_error(sess, kwargs)

    @classmethod
    async def update_or_create(
        cls,
        session: AsyncSession | None = None,
        defaults: dict | None = None,
        db_name: str = "default",
        **kwargs: Any,
    ) -> tuple[Self, bool]:
        """更新或创建数据（使用 UPSERT 锁）

        参数:
            session: 可选的数据库会话
            defaults: 默认值字典
            db_name: 数据库名称
            **kwargs: 查询条件

        返回:
            tuple[Self, bool]: 模型实例和是否为新创建
        """
        async with cls._managed_session(session, db_name) as sess:
            async with cls._lock_context(DbLockType.UPSERT):
                try:
                    stmt = build_filter_statement(cls, **kwargs).with_for_update()
                    result = await sess.execute(stmt)
                    instance = result.scalars().first()
                    if instance:
                        for key, value in (defaults or {}).items():
                            setattr(instance, key, value)
                        await sess.flush()
                        created = False
                    else:
                        async with nested_transaction(sess):
                            instance = cls(**kwargs, **(defaults or {}))
                            sess.add(instance)
                            await sess.flush()
                            await sess.refresh(instance)
                        created = True
                    await cls._invalidate_cache(instance)
                    return instance, created
                except IntegrityError:
                    return await cls._handle_integrity_error(sess, kwargs)

    async def save(
        self,
        session: AsyncSession | None = None,
        update_fields: Iterable[str] | None = None,
        force_create: bool = False,
        force_update: bool = False,
        db_name: str = "default",
    ):
        """保存数据（根据操作类型自动选择锁）

        参数:
            session: 可选的数据库会话
            update_fields: 要更新的字段列表（仅对已存在的记录有效）
            force_create: 强制创建（即使主键已存在也执行 INSERT）
            force_update: 强制更新（保留参数，主键存在时自动走 UPDATE 路径）
            db_name: 数据库名称
        """
        async with self._managed_session(session, db_name) as sess:
            pk_names = DbUtils.get_primary_key_names(self.__class__)
            pk_values = {name: getattr(self, name, None) for name in pk_names}
            is_new = any(value is None for value in pk_values.values())
            lock_type = DbLockType.CREATE if is_new else DbLockType.UPDATE

            async with self._lock_context(lock_type):
                if force_create or is_new:
                    # 新记录或强制创建：执行 INSERT
                    sess.add(self)
                    await sess.flush()
                    await sess.refresh(self)
                elif update_fields:
                    # 已存在的记录，仅更新指定字段
                    update_data = {
                        f: getattr(self, f) for f in update_fields if hasattr(self, f)
                    }
                    if update_data:
                        where_clause = and_(
                            getattr(self.__class__, name) == value
                            for name, value in pk_values.items()
                        )
                        stmt = (
                            update(self.__class__)
                            .where(where_clause)
                            .values(**update_data)
                        )
                        await sess.execute(stmt)
                        await sess.flush()
                        if self in sess:
                            await sess.refresh(self)
                else:
                    # 已存在的记录，全字段更新
                    merged = await sess.merge(self)
                    await sess.flush()
                    await sess.refresh(merged)

                await self.__class__._invalidate_cache(self)

    async def delete(
        self, session: AsyncSession | None = None, db_name: str = "default"
    ):
        """删除数据

        参数:
            session: 可选的数据库会话
            db_name: 数据库名称
        """
        async with self._managed_session(session, db_name) as sess:
            await sess.delete(self)
            await sess.flush()
            await self.__class__._invalidate_cache(self)

    @classmethod
    async def first_or_create(
        cls,
        session: AsyncSession | None = None,
        defaults: dict | None = None,
        db_name: str = "default",
        **kwargs: Any,
    ) -> tuple[Self, bool]:
        """获取第一条匹配记录，不存在则创建

        与 get_or_create 的区别：get_or_create 使用 filter_by 精确匹配，
        而 first_or_create 支持更灵活的查询条件。

        参数:
            session: 可选的数据库会话
            defaults: 创建时的默认值字典
            db_name: 数据库名称
            **kwargs: 查询条件

        返回:
            tuple[Self, bool]: 模型实例和是否为新创建
        """
        async with cls._managed_session(session, db_name) as sess:
            stmt = build_filter_statement(cls, **kwargs).limit(1)
            result = await sess.execute(stmt)
            instance = result.scalars().first()
            if instance:
                return instance, False
            try:
                async with nested_transaction(sess):
                    instance = cls(**kwargs, **(defaults or {}))
                    sess.add(instance)
                    await sess.flush()
                    await sess.refresh(instance)
                await cls._invalidate_cache(instance)
                return instance, True
            except IntegrityError:
                return await cls._handle_integrity_error(sess, kwargs)

    @classmethod
    async def safe_get_or_none(
        cls,
        *args,
        session: AsyncSession | None = None,
        clean_duplicates: bool = False,
        db_name: str = "default",
        **kwargs: Any,
    ) -> Self | None:
        """安全地获取一条记录或 None，处理重复记录

        参数:
            *args: SQLAlchemy 过滤表达式
            session: 可选的数据库会话
            clean_duplicates: 是否删除重复记录（默认 False，仅记录告警）。
                              设为 True 时会删除多余的重复记录，请谨慎使用。
            db_name: 数据库名称
            **kwargs: 查询参数，值为 None 时生成 IS NULL 条件

        返回:
            Self | None: 查询结果
        """
        async with cls._managed_session(session, db_name) as sess:
            base_stmt = build_filter_statement(cls, *args, **kwargs)
            try:
                result = await DbUtils.with_db_timeout(
                    sess.execute(base_stmt),
                    operation=f"{cls.__name__}.safe_get_or_none",
                    source="DataBaseModel",
                )
                records = result.scalars().all()
                match records:
                    case []:
                        return None
                    case [single]:
                        return single
                    case _ if hasattr(cls, "id"):
                        records.sort(key=lambda x: getattr(x, "id", 0), reverse=True)
                        logger.warning(
                            f"{cls.__name__} 发现 {len(records)} 条重复记录，"
                            f"返回最新一条 (id={getattr(records[0], 'id', None)})，"
                            f"建议检查数据唯一性约束",
                            LOG_COMMAND,
                        )
                        if clean_duplicates:
                            async with nested_transaction(sess):
                                for record in records[1:]:
                                    await sess.delete(record)
                                    logger.info(
                                        f"{cls.__name__} 删除重复记录: "
                                        f"id={getattr(record, 'id', None)}",
                                        LOG_COMMAND,
                                    )
                        return records[0]
                    case _:
                        return records[0]
            except TimeoutError:
                logger.error(
                    f"数据库操作超时: {cls.__name__}.safe_get_or_none",
                    LOG_COMMAND,
                )
                return None
            except Exception as e:
                logger.error(
                    f"数据库操作异常: {cls.__name__}.safe_get_or_none: {e!s}",
                    LOG_COMMAND,
                )
                raise
