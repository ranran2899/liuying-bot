"""数据库会话管理模块

提供多数据库连接的会话创建、获取、生命周期管理与监控能力。
所有会话管理逻辑封装在 ``SessionManager`` 类中，通过单例
``session_manager`` 暴露。
"""

import asyncio
import contextlib
import re
import traceback
from urllib.parse import urlparse

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from liuying.utils.log import logger

from .config import ENABLE_SESSION_TRACING, LOG_COMMAND
from .monitoring import leak_detector, pool_monitor
from .sync import sync_manager

_NAME_NORMALIZE_PATTERN = re.compile(r"[^a-z0-9_]+")


def _normalize_db_name(name: str) -> str:
    """规范化数据库名称

    转换为小写，将非字母数字下划线字符替换为下划线，并去除首尾下划线。
    空字符串或纯符号字符串返回 'default'。

    参数:
        name: 原始数据库名称

    返回:
        str: 规范化后的名称
    """
    normalized = _NAME_NORMALIZE_PATTERN.sub("_", name.lower()).strip("_")
    return normalized or "default"


_SQLITE_PRAGMAS = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA busy_timeout=30000",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA foreign_keys=ON",
)


async def _apply_sqlite_pragmas(driver_conn) -> None:
    """对原始驱动连接逐条执行 PRAGMA

    由 ``AdaptedConnection.run_async`` 调用，参数为原始
    aiosqlite 连接；操作经其内部队列提交到后台线程执行。
    """
    for pragma in _SQLITE_PRAGMAS:
        cursor = await driver_conn.execute(pragma)
        await cursor.close()


def _register_sqlite_pragma(engine: AsyncEngine) -> None:
    """注册 SQLite PRAGMA 事件监听器

    在每个新连接建立时设置：
    - ``journal_mode=WAL``：允许多读单写并发，避免读写互斥
    - ``busy_timeout=30000``：写锁竞争时等待 30 秒而非立即失败
    - ``synchronous=NORMAL``：WAL 模式下的推荐同步级别
    - ``foreign_keys=ON``：启用外键约束强制检查

    实现说明：同步事件回调中直接调用 aiosqlite 协程不会生效，
    因此使用 SQLAlchemy 公开的 ``AdaptedConnection.run_async``
    （自 1.4.30 起文档化的 API，专为连接池事件处理程序设计）
    执行全部 PRAGMA，不依赖适配器或驱动的任何私有属性。
    """

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record) -> None:
        try:
            dbapi_conn.run_async(_apply_sqlite_pragmas)
        except Exception as e:
            logger.warning(f"设置 SQLite PRAGMA 失败: {e}", LOG_COMMAND)


def _create_engine(db_url: str, config_params: dict) -> AsyncEngine:
    """根据 URL 创建异步引擎

    对 SQLite 额外注册 PRAGMA 事件监听器，从根源上避免并发写入时
    ``database is locked`` 错误。

    参数:
        db_url: 数据库连接 URL
        config_params: SQLAlchemy 引擎配置参数

    返回:
        AsyncEngine: 异步引擎实例
    """
    engine = create_async_engine(db_url, **config_params)
    scheme = urlparse(db_url).scheme
    if scheme.startswith("sqlite"):
        _register_sqlite_pragma(engine)
    return engine


class SessionManager:
    """数据库会话管理器，支持多个数据库连接

    负责引擎与会话工厂的创建、表结构按需创建与连接生命周期管理，
    并委托 ``monitoring`` 模块执行连接池/泄漏监控的启停注册，
    通过单例 ``session_manager`` 暴露，外部统一通过该单例调用。
    """

    __slots__ = (
        "_monitoring_enabled",
        "_table_creation_lock",
        "db_tables_created",
        "engines",
        "sessionmakers",
    )

    def __init__(self):
        self.engines: dict[str, AsyncEngine] = {}
        self.sessionmakers: dict[str, async_sessionmaker] = {}
        self.db_tables_created: dict[str, bool] = {}
        self._table_creation_lock = asyncio.Lock()
        self._monitoring_enabled = False

    async def init(self, db_url: str, config_params: dict, db_name: str = "default"):
        """初始化指定名称的数据库连接

        创建异步引擎并注册会话工厂，db_name 会经过规范化处理。
        对 SQLite 额外注册 PRAGMA 事件监听器。

        参数:
            db_url: 数据库连接字符串
            config_params: 配置参数
            db_name: 数据库名称
        """
        normalized_name = _normalize_db_name(db_name)
        engine = _create_engine(db_url, config_params)
        sessionmaker_obj = async_sessionmaker(
            bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
        )
        self.engines[normalized_name] = engine
        self.sessionmakers[normalized_name] = sessionmaker_obj
        self.db_tables_created[normalized_name] = False
        pool_monitor.register_engine(normalized_name, engine)

    async def start_monitoring(self):
        """启动连接池和泄漏监控"""
        if self._monitoring_enabled:
            return
        await pool_monitor.start_monitoring()
        await leak_detector.start_monitoring()
        self._monitoring_enabled = True

    async def stop_monitoring(self):
        """停止连接池和泄漏监控"""
        await pool_monitor.stop_monitoring()
        await leak_detector.stop_monitoring()
        self._monitoring_enabled = False

    async def ensure_tables_created(self, db_name: str = "default"):
        """确保指定数据库的表已创建（按需创建）

        db_name 会经过规范化处理，与 ``init`` 的键保持一致。

        参数:
            db_name: 数据库名称
        """
        normalized_name = _normalize_db_name(db_name)
        if normalized_name == "default":
            return
        if self.db_tables_created.get(normalized_name, False):
            return
        async with self._table_creation_lock:
            if self.db_tables_created.get(normalized_name, False):
                return
            if normalized_name in self.engines:
                # 循环依赖：base_model 导入 session_manager，session 按需导入 Base
                from .base_model import Base

                logger.debug(
                    f"为数据库 {normalized_name} 按需创建表结构...", LOG_COMMAND
                )
                async with self.engines[normalized_name].begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                self.db_tables_created[normalized_name] = True
                logger.debug(f"数据库 {normalized_name} 表结构创建完成", LOG_COMMAND)

    def get_session(self, db_name: str = "default") -> "DatabaseSessionManager":
        """获取指定数据库的会话管理器

        db_name 会经过规范化处理，与 ``init`` 注册的键保持一致，
        因此传入 ``"Log_DB"`` 与 ``"log_db"`` 等价。

        参数:
            db_name: 数据库名称

        返回:
            DatabaseSessionManager: 会话管理器

        异常:
            RuntimeError: 数据库尚未初始化
        """
        normalized_name = _normalize_db_name(db_name)
        if normalized_name not in self.sessionmakers:
            raise RuntimeError(f"数据库 {normalized_name} 尚未初始化")
        return DatabaseSessionManager(
            self.sessionmakers[normalized_name], normalized_name, self
        )

    async def disconnect(self, db_name: str | None = None):
        """关闭数据库连接，如果未指定则关闭所有连接

        db_name 会经过规范化处理，与 ``init`` 的键保持一致。

        参数:
            db_name: 数据库名称，为None时关闭所有
        """
        if db_name is not None:
            normalized_name = _normalize_db_name(db_name)
            if normalized_name not in self.engines:
                return
            pool_monitor.unregister_engine(normalized_name)
            await self.engines[normalized_name].dispose()
            del self.engines[normalized_name]
            del self.sessionmakers[normalized_name]
            self.db_tables_created.pop(normalized_name, None)
            logger.info(f"数据库 {normalized_name} 已成功断开连接", LOG_COMMAND)
            return

        await sync_manager.stop_sync()
        logger.info("数据库同步任务已停止", LOG_COMMAND)
        await self.stop_monitoring()

        for name in self.engines:
            pool_monitor.unregister_engine(name)
        for engine in self.engines.values():
            await engine.dispose()
        self.engines.clear()
        self.sessionmakers.clear()
        self.db_tables_created.clear()
        logger.info("所有数据库已成功断开连接", LOG_COMMAND)


class DatabaseSessionManager:
    """数据库会话管理器，支持异步上下文管理器模式"""

    __slots__ = ("_session_id", "db_name", "session", "session_manager", "sessionmaker")

    def __init__(
        self,
        sessionmaker: async_sessionmaker,
        db_name: str = "default",
        session_manager: SessionManager | None = None,
    ):
        """初始化会话管理器

        参数:
            sessionmaker: 异步会话工厂
            db_name: 数据库名称
            session_manager: 所属会话管理器
        """
        self.sessionmaker = sessionmaker
        self.db_name = db_name
        self.session_manager = session_manager
        self._session_id: int | None = None
        self.session: AsyncSession | None = None

    async def __aenter__(self) -> AsyncSession:
        """进入异步上下文时创建会话"""
        if self.session_manager:
            await self.session_manager.ensure_tables_created(self.db_name)
        self.session = self.sessionmaker()
        self._session_id = id(self.session)
        trace_info = (
            "".join(traceback.format_stack()[-5:-2])
            if ENABLE_SESSION_TRACING
            else "追踪已禁用"
        )
        leak_detector.register_session(self.db_name, self._session_id, trace_info)
        return self.session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出异步上下文时处理会话

        正常退出时提交，异常时回滚。提交失败必须向上抛出，
        避免调用方误认为写操作成功。
        """
        try:
            match exc_type:
                case None:
                    await self.session.commit()
                case _:
                    await self.session.rollback()
                    logger.debug(
                        f"数据库会话回滚: {self.db_name}, "
                        f"原因: {exc_type.__name__}: {exc_val}",
                        LOG_COMMAND,
                    )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"数据库会话提交失败: {self.db_name}, {e}", LOG_COMMAND)
            raise
        finally:
            if self._session_id:
                leak_detector.unregister_session(self._session_id)
            try:
                await self.session.close()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"数据库会话关闭异常: {self.db_name}, {e}", LOG_COMMAND)


session_manager = SessionManager()
"""会话管理器单例，外部统一通过此单例访问会话相关能力"""


@contextlib.asynccontextmanager
async def nested_transaction(session: AsyncSession):
    """事务保存点（嵌套事务）上下文管理器

    在已有会话中创建保存点，异常时仅回滚到保存点而非整个事务。

    参数:
        session: 已有的数据库会话

    返回:
        AsyncSession: 同一会话（在保存点保护下）

    使用示例:
        async with session_manager.get_session() as session:
            await session.execute(...)
            async with nested_transaction(session) as nested:
                await nested.execute(...)
                # 如果此处异常，仅回滚到保存点
            await session.execute(...)
    """
    nested = await session.begin_nested()
    try:
        yield session
        await nested.commit()
    except Exception:
        await nested.rollback()
        raise
