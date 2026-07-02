"""数据库配置模块

集中管理数据库相关配置常量、连接池参数 dataclass 与引擎配置生成函数。
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlparse

from liuying.configs.config import BotConfig

from .exceptions import DbUrlIsNone

DB_TIMEOUT_SECONDS = 3.0
SLOW_QUERY_THRESHOLD = 0.5
LOG_COMMAND = "db_liuying"
ENABLE_SESSION_TRACING = False
DB_CONNECT_MAX_RETRIES = 3
DB_CONNECT_RETRY_DELAY = 5.0


@dataclass(frozen=True, slots=True)
class QueryTimeoutConfig:
    """查询超时配置"""

    max_retries: int = 5
    base_delay: float = 1.0


@dataclass(frozen=True, slots=True)
class PostgreSQLConfig:
    """PostgreSQL连接池配置"""

    max_size: int = 30
    min_size: int = 5
    pool_recycle: int = 3600


@dataclass(frozen=True, slots=True)
class MySQLConfig:
    """MySQL连接配置"""

    max_connections: int = 20
    connect_timeout: int = 30


@dataclass(frozen=True, slots=True)
class SQLiteConfig:
    """SQLite连接池配置

    注意：``journal_mode`` 与 ``busy_timeout`` 由 ``connection_registry``
    的 PRAGMA 事件监听器设置，不通过 ``connect_args`` 传递（后者不是
    ``sqlite3.connect`` 的合法参数）。
    """

    timeout: int = 30
    pool_size: int = 20
    max_overflow: int = 10
    pool_recycle: int = 3600
    pool_pre_ping: bool = True


QUERY_TIMEOUT_SECONDS = QueryTimeoutConfig()
POSTGRESQL_CONFIG = PostgreSQLConfig()
MYSQL_CONFIG = MySQLConfig()
SQLITE_CONFIG = SQLiteConfig()


@dataclass(slots=True)
class DbModel:
    """模型注册配置"""

    script_methods: list[tuple[str, Callable]] = field(default_factory=list)
    models: list[str] = field(default_factory=list)


db_model = DbModel()

prompt = """
**********************************************************************
  **************************** 配置为空 *************************
  请打开 WebUi 进行基础配置
  配置地址：http://{{host}}:{{port}}/#/configure
***********************************************************************
***********************************************************************
""".strip()


def get_config(db_url: str | None = None) -> dict:
    """获取数据库引擎配置参数

    根据数据库连接 URL 的 scheme 选择对应的连接池配置，返回 SQLAlchemy
    ``create_async_engine`` 所需的参数字典。

    参数:
        db_url: 数据库连接字符串，如果为None则使用 BotConfig.db_url

    返回:
        dict: 数据库引擎配置参数

    抛出:
        DbUrlIsNone: 数据库连接字符串为空
    """
    current_db_url = db_url or BotConfig.db_url
    if not current_db_url:
        raise DbUrlIsNone("数据库Url连接字符串为空，请检查配置文件（.env）")

    parsed = urlparse(current_db_url)
    config_params: dict = {"echo": False, "pool_pre_ping": True}

    match parsed.scheme:
        case s if s.startswith("postgres"):
            config_params.update(
                {
                    "pool_size": POSTGRESQL_CONFIG.max_size,
                    "max_overflow": (
                        POSTGRESQL_CONFIG.max_size - POSTGRESQL_CONFIG.min_size
                    ),
                    "pool_recycle": POSTGRESQL_CONFIG.pool_recycle,
                }
            )
        case "mysql":
            config_params.update(
                {
                    "pool_size": MYSQL_CONFIG.max_connections,
                    "connect_args": {"connect_timeout": MYSQL_CONFIG.connect_timeout},
                }
            )
        case "sqlite":
            config_params.update(
                {
                    "pool_size": SQLITE_CONFIG.pool_size,
                    "max_overflow": SQLITE_CONFIG.max_overflow,
                    "pool_recycle": SQLITE_CONFIG.pool_recycle,
                    "pool_pre_ping": SQLITE_CONFIG.pool_pre_ping,
                    "connect_args": {
                        "check_same_thread": False,
                        "timeout": SQLITE_CONFIG.timeout,
                    },
                }
            )

    return config_params
