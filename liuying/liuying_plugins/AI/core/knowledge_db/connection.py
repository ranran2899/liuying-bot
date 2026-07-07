"""知识库 SQLite 连接管理

提供独立的 aiosqlite 连接管理，与 liuying_db 完全解耦。
启用 WAL 模式防止 ``database is locked`` 错误，串行化写操作
避免 SQLite 并发锁冲突。
"""

import asyncio
from collections.abc import Awaitable, Callable
import functools
import sqlite3

import aiosqlite

from liuying.configs.path_config import DB_PATH
from liuying.utils.log import logger

from .schema import ALL_DDL

_KB_DB_FILE = DB_PATH / "knowledge_base.db"
"""知识库 SQLite 数据库文件路径"""

_KB_PRAGMAS: list[str] = [
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA busy_timeout=5000",
    "PRAGMA foreign_keys=ON",
]
"""SQLite PRAGMA 配置，WAL 模式 + 忙等待"""

_WRITE_MAX_RETRIES = 4
"""写操作最大重试次数（含首次执行）"""

_WRITE_BASE_DELAY = 0.15
"""写操作重试初始延迟（秒），每次翻倍"""

_LOG_CMD = "knowledge_base"
"""日志 command 标识"""


def _is_locked_error(exc: Exception) -> bool:
    """判断异常是否为 SQLite database is locked 错误

    参数:
        exc: 异常实例

    返回:
        bool: 是否为锁冲突错误
    """
    for err in (exc, exc.__cause__, exc.__context__):
        if isinstance(err, sqlite3.OperationalError):
            msg = str(err).lower()
            if "database is locked" in msg or "is locked" in msg:
                return True
    return False


def with_write_lock(func: Callable[..., Awaitable[None]]):
    """装饰器：为写操作添加全局写锁与重试机制

    串行化所有写操作，遇到 ``database is locked`` 时自动重试（指数退避）。
    """

    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs) -> None:
        async with self._conn.write_lock:
            for attempt in range(_WRITE_MAX_RETRIES):
                try:
                    await func(self, *args, **kwargs)
                    return
                except Exception as e:
                    if not (
                        _is_locked_error(e)
                        and attempt < _WRITE_MAX_RETRIES - 1
                    ):
                        raise
                    delay = _WRITE_BASE_DELAY * (2**attempt)
                    logger.debug(
                        f"知识库写锁冲突，{delay:.2f}s 后重试 "
                        f"({attempt + 1}/{_WRITE_MAX_RETRIES}): {e}",
                        _LOG_CMD,
                    )
                    await asyncio.sleep(delay)

    return wrapper


class KbConnectionManager:
    """知识库连接管理器

    管理独立的 aiosqlite 连接，启用 WAL 模式，
    提供全局写锁以串行化写操作。

    通过单例 ``kb_connection`` 暴露，外部统一通过该单例访问。
    """

    __slots__ = ("_db", "_initialized", "write_lock")

    def __init__(self) -> None:
        self._db: aiosqlite.Connection | None = None
        self.write_lock = asyncio.Lock()
        self._initialized = False

    async def init(self) -> None:
        """初始化数据库连接与表结构

        幂等操作，重复调用安全。创建数据库文件、设置 PRAGMA、
        执行全部建表 DDL。
        """
        if self._initialized:
            return
        DB_PATH.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(_KB_DB_FILE))
        self._db.row_factory = aiosqlite.Row
        for pragma in _KB_PRAGMAS:
            await self._db.execute(pragma)
        await self._db.commit()
        for ddl in ALL_DDL:
            await self._db.execute(ddl)
        await self._db.commit()
        self._initialized = True
        logger.info("知识库数据库初始化完成", _LOG_CMD)

    @property
    def db(self) -> aiosqlite.Connection:
        """获取数据库连接

        返回:
            aiosqlite.Connection: 数据库连接

        抛出:
            RuntimeError: 未初始化时调用
        """
        if self._db is None:
            raise RuntimeError(
                "知识库数据库未初始化，请先调用 init()"
            )
        return self._db

    async def close(self) -> None:
        """关闭数据库连接"""
        if self._db is not None:
            await self._db.close()
            self._db = None
            self._initialized = False
            logger.info("知识库数据库连接已关闭", _LOG_CMD)


kb_connection = KbConnectionManager()
"""知识库连接管理器单例"""
