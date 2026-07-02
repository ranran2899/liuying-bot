"""数据库会话管理模块

提供多数据库连接的会话创建、获取、生命周期管理与监控能力。
所有会话管理逻辑封装在 ``SessionManager`` 类中，通过单例
``session_manager`` 暴露，避免散装函数导入。
"""

import asyncio
from collections.abc import Callable
import contextlib
import traceback
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from liuying.utils.log import logger

from .config import ENABLE_SESSION_TRACING, LOG_COMMAND
from .connection_registry import connection_registry
from .monitoring import leak_detector, pool_monitor
from .sync import sync_manager


class SessionManager:
    """数据库会话管理器，支持多个数据库连接

    负责会话创建、连接池监控、健康检查与泄漏检测等能力，
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

        使用 ``connection_registry`` 注册的工厂创建 engine。
        db_name 会经过 ``normalize_db_name`` 规范化。

        参数:
            db_url: 数据库连接字符串
            config_params: 配置参数
            db_name: 数据库名称
        """
        normalized_name = connection_registry.normalize_db_name(db_name)
        engine = connection_registry.create_engine(db_url, config_params)
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

        参数:
            db_name: 数据库名称
        """
        if db_name == "default":
            return

        if self.db_tables_created.get(db_name, False):
            return

        async with self._table_creation_lock:
            if self.db_tables_created.get(db_name, False):
                return

            if db_name in self.engines:
                # 循环依赖：base_model 导入 session_manager，session 按需导入 Base
                from .base_model import Base

                logger.debug(f"为数据库 {db_name} 按需创建表结构...", LOG_COMMAND)
                async with self.engines[db_name].begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                self.db_tables_created[db_name] = True
                logger.debug(f"数据库 {db_name} 表结构创建完成", LOG_COMMAND)

    def get_session(self, db_name: str = "default") -> "DatabaseSessionManager":
        """获取指定数据库的会话管理器

        参数:
            db_name: 数据库名称

        返回:
            DatabaseSessionManager: 会话管理器
        """
        if db_name not in self.sessionmakers:
            raise RuntimeError(f"数据库 {db_name} 尚未初始化")
        return DatabaseSessionManager(self.sessionmakers[db_name], db_name, self)

    async def disconnect(self, db_name: str | None = None):
        """关闭数据库连接，如果未指定则关闭所有连接

        参数:
            db_name: 数据库名称，为None时关闭所有
        """
        if db_name is not None:
            if db_name not in self.engines:
                return
            pool_monitor.unregister_engine(db_name)
            await self.engines[db_name].dispose()
            del self.engines[db_name]
            del self.sessionmakers[db_name]
            self.db_tables_created.pop(db_name, None)
            logger.info(f"数据库 {db_name} 已成功断开连接", LOG_COMMAND)
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

    def _get_pool_info(self, db_name: str) -> dict | None:
        """获取指定数据库连接池信息

        参数:
            db_name: 数据库名称

        返回:
            dict | None: 连接池信息
        """
        if db_name not in self.engines:
            return None

        pool = self.engines[db_name].pool
        return {
            "db_name": db_name,
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "is_valid": pool.status() if hasattr(pool, "status") else None,
        }

    def get_pool_status(self, db_name: str = "default") -> dict | None:
        """获取指定数据库的连接池状态

        参数:
            db_name: 数据库名称

        返回:
            dict | None: 连接池状态信息，如果数据库不存在则返回None
        """
        return self._get_pool_info(db_name)

    def get_all_pool_status(self) -> dict[str, dict]:
        """获取所有数据库的连接池状态

        返回:
            dict[str, dict]: 各数据库连接池状态信息
        """
        return {name: self._get_pool_info(name) for name in self.engines}

    async def health_check(self, db_name: str = "default") -> dict[str, Any]:
        """检查指定数据库的健康状态

        参数:
            db_name: 数据库名称

        返回:
            dict: 健康检查结果
        """
        result: dict[str, Any] = {"db_name": db_name, "healthy": False, "error": None}

        if db_name not in self.engines:
            result["error"] = f"数据库 {db_name} 尚未初始化"
            return result

        try:
            async with self.get_session(db_name) as session:
                await session.execute(text("SELECT 1"))
            result["healthy"] = True
            result["health_score"] = pool_monitor.get_health_score(db_name)
        except Exception as e:
            result["error"] = str(e)
            logger.warning(f"数据库 {db_name} 健康检查失败: {e}", LOG_COMMAND)

        return result

    async def health_check_all(self) -> dict[str, dict[str, Any]]:
        """检查所有数据库的健康状态

        返回:
            dict[str, dict]: 各数据库健康检查结果
        """
        return {name: await self.health_check(name) for name in self.engines}

    def get_leak_stats(self) -> dict:
        """获取连接泄漏检测统计信息

        返回:
            dict: 统计信息
        """
        return leak_detector.get_stats()

    def get_recent_alerts(self, count: int = 10) -> list:
        """获取最近的连接池告警

        参数:
            count: 获取数量

        返回:
            list: 告警列表
        """
        return pool_monitor.get_recent_alerts(count)

    def add_alert_callback(self, callback: Callable):
        """添加连接池告警回调

        参数:
            callback: 回调函数
        """
        pool_monitor.add_alert_callback(callback)

    def add_leak_callback(self, callback: Callable):
        """添加连接泄漏回调

        参数:
            callback: 回调函数
        """
        leak_detector.add_leak_callback(callback)


class DatabaseSessionManager:
    """数据库会话管理器，支持异步上下文管理器模式"""

    __slots__ = ("_session_id", "db_name", "session", "session_manager", "sessionmaker")

    def __init__(
        self,
        sessionmaker: async_sessionmaker,
        db_name: str = "default",
        session_manager: SessionManager | None = None,
    ):
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
        """退出异步上下文时处理会话"""
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
        except Exception as e:
            logger.warning(f"数据库会话提交/回滚异常: {self.db_name}, {e}", LOG_COMMAND)
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
    适用于复杂业务中需要部分回滚的场景。

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
