"""数据库连接接口扩展机制

允许第三方开发者注册自定义数据库连接工厂，提供数据库名称规范化能力，
确保新接口与现有系统兼容。

注册的工厂按 URL scheme 前缀匹配（如 'sqlite' 匹配
'sqlite+aiosqlite'、'sqlite+pysqlite' 等）。内置三个工厂：
SQLite / MySQL / PostgreSQL，分别调用 ``create_async_engine``。

使用示例:
    ```python
    from liuying.services.liuying_db import connection_registry
    from sqlalchemy.ext.asyncio import create_async_engine

    def my_sqlite_factory(url: str, params: dict):
        # 加载 sqlite-vec 扩展等自定义逻辑
        return create_async_engine(url, **params)

    # 注册后覆盖内置 sqlite 工厂
    connection_registry.register('sqlite', my_sqlite_factory)
    ```
"""

from collections.abc import Callable
import re
from urllib.parse import urlparse

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from liuying.utils.log import logger

from .config import LOG_COMMAND

_ConnectionFactory = Callable[[str, dict], AsyncEngine]
"""连接工厂类型：(db_url, config_params) -> AsyncEngine"""

_NAME_NORMALIZE_PATTERN = re.compile(r"[^a-z0-9_]+")
"""数据库名称合法字符匹配（小写字母/数字/下划线）"""


def _create_sqlite_engine(db_url: str, config_params: dict) -> AsyncEngine:
    """内置 SQLite 连接工厂

    创建引擎后注册 PRAGMA 事件监听器，确保每个新连接都启用
    WAL 模式、忙等待与异步同步策略，从根源上避免并发写入时
    ``database is locked`` 错误。
    """
    engine = create_async_engine(db_url, **config_params)
    _register_sqlite_pragma(engine)
    return engine


def _register_sqlite_pragma(engine: AsyncEngine) -> None:
    """注册 SQLite PRAGMA 事件监听器

    在每个新连接建立时设置：
    - ``journal_mode=WAL``：允许多读单写并发，避免读写互斥
    - ``busy_timeout=30000``：写锁竞争时等待 30 秒而非立即失败
    - ``synchronous=NORMAL``：WAL 模式下的推荐同步级别

    注意：``connect_args`` 中的 ``journal_mode`` 不是 ``sqlite3.connect``
    的合法参数，必须通过 PRAGMA 设置才能生效。
    """

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record) -> None:
        """连接建立时设置 PRAGMA"""
        # 导航到底层 sqlite3.Connection（穿透两层适配器）：
        # AsyncAdapt_aiosqlite_connection._connection -> aiosqlite.Connection
        # aiosqlite.Connection._connection -> sqlite3.Connection
        underlying = dbapi_conn
        while hasattr(underlying, "_connection") and underlying._connection is not None:
            underlying = underlying._connection
        try:
            underlying.execute("PRAGMA journal_mode=WAL")
            underlying.execute("PRAGMA busy_timeout=30000")
            underlying.execute("PRAGMA synchronous=NORMAL")
        except Exception as e:
            logger.debug(
                f"设置 SQLite PRAGMA 失败（连接仍可用）: {e}",
                LOG_COMMAND,
            )


def _create_mysql_engine(db_url: str, config_params: dict) -> AsyncEngine:
    """内置 MySQL 连接工厂"""
    return create_async_engine(db_url, **config_params)


def _create_postgres_engine(db_url: str, config_params: dict) -> AsyncEngine:
    """内置 PostgreSQL 连接工厂"""
    return create_async_engine(db_url, **config_params)


class ConnectionRegistry:
    """数据库连接工厂注册中心

    管理内置与用户注册的连接工厂，按 URL scheme 前缀匹配选择工厂创建引擎,
    并提供数据库名称规范化能力。通过单例 ``connection_registry`` 暴露。
    """

    __slots__ = ("_builtin_factories", "_registry")

    def __init__(self) -> None:
        self._registry: dict[str, _ConnectionFactory] = {}
        self._builtin_factories: dict[str, _ConnectionFactory] = {
            "sqlite": _create_sqlite_engine,
            "mysql": _create_mysql_engine,
            "postgres": _create_postgres_engine,
            "postgresql": _create_postgres_engine,
        }

    def register(self, scheme: str, factory: _ConnectionFactory) -> None:
        """注册数据库连接工厂

        注册后该 scheme 的连接创建将走自定义工厂，覆盖内置实现。
        调用 ``unregister`` 可回退到内置。

        参数:
            scheme: URL scheme（如 'sqlite'、'postgres'、'mysql'），不区分大小写
            factory: 工厂函数 (db_url, config_params) -> AsyncEngine
        """
        scheme_lower = scheme.lower()
        self._registry[scheme_lower] = factory
        logger.debug(
            f"已注册数据库连接工厂: scheme={scheme_lower}",
            LOG_COMMAND,
        )

    def unregister(self, scheme: str) -> _ConnectionFactory | None:
        """注销用户注册的工厂，回退到内置

        参数:
            scheme: URL scheme

        返回:
            _ConnectionFactory | None: 被移除的工厂，不存在返回 None
        """
        return self._registry.pop(scheme.lower(), None)

    def get_factory(self, scheme: str) -> _ConnectionFactory | None:
        """获取指定 scheme 的连接工厂

        优先返回用户注册的工厂，其次返回内置工厂。

        参数:
            scheme: URL scheme（可为 'sqlite+aiosqlite' 等复合形式，
                    自动取 '+' 前部分）

        返回:
            _ConnectionFactory | None: 工厂函数，未注册返回 None
        """
        base = (scheme or "").split("+", 1)[0].lower()
        return self._registry.get(base) or self._builtin_factories.get(base)

    def list_schemes(self) -> list[str]:
        """列出所有可用的 scheme（含内置与用户注册）

        返回:
            list[str]: scheme 列表（小写，排序）
        """
        seen: set[str] = set()
        seen.update(self._registry.keys())
        seen.update(self._builtin_factories.keys())
        return sorted(seen)

    def create_engine(
        self, db_url: str, config_params: dict
    ) -> AsyncEngine:
        """根据 URL 自动选择注册的工厂创建 engine

        未注册的 scheme 回退到 ``create_async_engine``。

        参数:
            db_url: 数据库连接 URL
            config_params: 配置参数

        返回:
            AsyncEngine: 异步引擎实例
        """
        parsed = urlparse(db_url)
        factory = self.get_factory(parsed.scheme)
        if factory is not None:
            return factory(db_url, config_params)
        return create_async_engine(db_url, **config_params)

    @staticmethod
    def normalize_db_name(name: str) -> str:
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


connection_registry = ConnectionRegistry()
"""连接工厂注册中心单例"""
