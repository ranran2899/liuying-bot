"""数据库生命周期管理模块

负责数据库连接的初始化、表结构创建、脚本执行与同步任务启动，
包含自动重试机制。所有初始化逻辑封装在 ``LifecycleManager`` 类中，
通过模块级 ``init`` 函数对接 NoneBot 启动钩子。
"""

import asyncio
import inspect

import nonebot
from nonebot.utils import is_coroutine_callable
from sqlalchemy import text

from liuying.configs.config import BotConfig
from liuying.utils.log import logger

from .base_model import Base
from .config import (
    DB_CONNECT_MAX_RETRIES,
    DB_CONNECT_RETRY_DELAY,
    LOG_COMMAND,
    db_model,
    get_config,
    prompt,
)
from .exceptions import DbConnectError, DbUrlIsNone
from .session import session_manager
from .sync import sync_manager
from .utils import DbUtils

driver = nonebot.get_driver()

# 各方言“迁移已应用 / 对象不存在”的良性错误特征。
# 脚本先于 create_all 执行：新装库缺表、旧装库列已存在或已删除均会报错，
# 识别后静默跳过；语法错误等真实故障不在此列，必须显式告警。
_BENIGN_SQLITE_KEYWORDS = (
    "duplicate column",
    "already exists",
    "no such column",
    "no such table",
)
_BENIGN_POSTGRES_CODES = frozenset({"42701", "42703", "42P01", "42P06", "42P07"})
_BENIGN_MYSQL_CODES = frozenset({1050, 1060, 1091, 1146})


def _is_benign_migration_error(error: Exception, dialect: str) -> bool:
    """判断迁移失败是否属于“已应用过 / 对象不存在”的可忽略情况

    参数:
        error: SQLAlchemy 包装后的数据库异常
        dialect: 数据库方言名（sqlite/postgresql/mysql）

    返回:
        bool: 是否为可忽略的幂等迁移错误
    """
    orig = getattr(error, "orig", None)
    match dialect:
        case "sqlite":
            message = str(orig).lower()
            return any(k in message for k in _BENIGN_SQLITE_KEYWORDS)
        case "postgresql":
            return getattr(orig, "pgcode", None) in _BENIGN_POSTGRES_CODES
        case "mysql" | "mariadb":
            args = getattr(orig, "args", ())
            return bool(args) and args[0] in _BENIGN_MYSQL_CODES
        case _:
            return False


class LifecycleManager:
    """数据库生命周期管理器

    封装数据库初始化、表结构创建、脚本执行与同步任务启动等逻辑,
    由模块级 ``init`` 函数在 NoneBot 启动时调用。
    """

    __slots__ = ()

    @staticmethod
    async def _run_script_methods():
        """运行脚本方法

        支持模型在 `_run_script(cls, db_name="default")` 中根据目标库返回 SQL，
        未声明 `db_name` 参数的脚本仅会在默认数据库执行，保持向后兼容。

        注意: 脚本先于 ``create_all`` 执行。全新安装时引用新表的脚本会因
        表不存在而失败，属预期行为（create_all 随后会带上新字段建表，
        结果自愈）；已安装库上的重复迁移失败同样被容忍并跳过。

        每条 SQL 独立提交，失败后必须显式回滚：PostgreSQL/MySQL 上失败
        语句会使事务进入中止态，不回滚将导致后续脚本全部级联失败。
        良性幂等错误（列已存在、列/表不存在、对象已存在）仅记 debug，
        其余错误逐条输出 warning 并在库维度汇总，避免真实迁移故障被
        “可能为已应用过的迁移”的汇总告警长期掩盖。
        """
        if not db_model.script_methods:
            return

        logger.debug(f"即将运行脚本方法, 合计 {len(db_model.script_methods)} 个...")

        scripts_by_db: dict[str, list[str]] = {}

        for module, func in db_model.script_methods:
            try:
                sig = inspect.signature(func)
                supports_db_name = "db_name" in sig.parameters
            except ValueError:
                supports_db_name = False

            for db_name in session_manager.engines:
                if not supports_db_name and db_name != "default":
                    continue
                try:
                    if supports_db_name:
                        sql = (
                            await func(db_name=db_name)
                            if is_coroutine_callable(func)
                            else func(db_name=db_name)
                        )
                    else:
                        sql = await func() if is_coroutine_callable(func) else func()
                    if sql:
                        # 归一化为列表，防止脚本方法误返回字符串被逐字符拆开
                        scripts_by_db.setdefault(db_name, []).extend(
                            [sql] if isinstance(sql, str) else sql
                        )
                except Exception as e:
                    logger.warning(
                        f"{module} 在数据库 {db_name} 执行脚本方法出错",
                        LOG_COMMAND,
                        e=e,
                    )

        for db_name, sql_list in scripts_by_db.items():
            skipped = 0
            failed_sqls: list[tuple[str, Exception]] = []
            async with session_manager.get_session(db_name) as session:
                dialect = session.bind.dialect.name if session.bind else "unknown"
                for sql in sql_list:
                    logger.debug(f"执行SQL: {sql}", LOG_COMMAND)
                    try:
                        await DbUtils.with_db_timeout(
                            session.execute(text(sql)),
                            operation=f"执行SQL: {sql[:50]}...",
                        )
                        await session.commit()
                    except Exception as e:
                        # 回滚失败语句，恢复事务可用状态，防止后续脚本级联失败
                        await session.rollback()
                        if _is_benign_migration_error(e, dialect):
                            skipped += 1
                            logger.debug(
                                f"迁移已应用，跳过: {sql}", LOG_COMMAND, e=e
                            )
                        else:
                            failed_sqls.append((sql, e))
                            logger.warning(
                                f"迁移 SQL 执行失败: {sql}", LOG_COMMAND, e=e
                            )
            if skipped:
                logger.debug(
                    f"数据库 {db_name} 有 {skipped} 条迁移已应用，自动跳过",
                    LOG_COMMAND,
                )
            if failed_sqls:
                logger.warning(
                    f"数据库 {db_name} 有 {len(failed_sqls)} 条迁移 SQL "
                    f"执行失败，请检查上方具体错误",
                    LOG_COMMAND,
                )

        if scripts_by_db:
            logger.debug("脚本方法执行完毕!")

    @staticmethod
    async def _create_default_tables():
        """创建默认数据库表结构"""
        logger.debug("开始生成默认数据库表结构...")
        if "default" in session_manager.engines:
            async with session_manager.engines["default"].begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            session_manager.db_tables_created["default"] = True
        logger.debug("默认数据库表结构生成完毕!")

    @staticmethod
    async def _init_extra_databases():
        """初始化额外数据库连接"""
        if not BotConfig.db_urls:
            return

        logger.debug(f"即将初始化 {len(BotConfig.db_urls)} 个额外数据库连接...")
        for db_name, db_url in BotConfig.db_urls.items():
            try:
                config_params = get_config(db_url)
                await session_manager.init(db_url, config_params, db_name)
                logger.debug(f"数据库 {db_name} 初始化成功!")
            except Exception as e:
                logger.error(f"数据库 {db_name} 初始化失败: {e}")

    @staticmethod
    async def _start_sync_if_enabled():
        """如果启用则启动数据库同步"""
        if not BotConfig.db_sync_enabled:
            logger.info("数据库同步功能已禁用，跳过同步任务启动")
            return

        if BotConfig.db_sync_slaves:
            logger.info(f"启动数据库同步，同步副数据库: {BotConfig.db_sync_slaves}")
            await sync_manager.start_sync(
                BotConfig.db_sync_slaves,
                BotConfig.db_sync_interval,
            )

    @staticmethod
    async def initialize():
        """执行完整的数据库初始化流程

        包含主数据库连接、额外数据库连接、脚本执行、表结构创建、
        监控启动与同步任务启动，带自动重试机制。

        异常:
            DbUrlIsNone: 数据库连接字符串为空
            DbConnectError: 数据库连接失败（已重试最大次数）
        """
        if not BotConfig.db_url:
            error = prompt.format(host=driver.config.host, port=driver.config.port)
            raise DbUrlIsNone("\n" + error.strip())

        last_error = None
        for attempt in range(1, DB_CONNECT_MAX_RETRIES + 1):
            try:
                # 重试前清理上一次失败可能残留的引擎与同步任务，避免资源泄漏
                if attempt > 1 and session_manager.engines:
                    await sync_manager.stop_sync()
                    await session_manager.disconnect()
                await session_manager.init(BotConfig.db_url, get_config())
                await LifecycleManager._init_extra_databases()
                await LifecycleManager._run_script_methods()
                await LifecycleManager._create_default_tables()

                db_count = len(session_manager.engines)
                logger.info(f"数据库加载成功！共初始化 {db_count} 个数据库连接")

                await session_manager.start_monitoring()
                logger.info("数据库连接池监控已启动")

                await LifecycleManager._start_sync_if_enabled()
                return

            except DbUrlIsNone:
                raise
            except Exception as e:
                last_error = e
                if attempt < DB_CONNECT_MAX_RETRIES:
                    delay = DB_CONNECT_RETRY_DELAY * attempt
                    logger.warning(
                        f"数据库连接失败 (第{attempt}/{DB_CONNECT_MAX_RETRIES}次)，"
                        f"{delay}秒后重试: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"数据库连接失败，已重试{DB_CONNECT_MAX_RETRIES}次: {e}"
                    )

        err_msg = f"数据库连接错误（已重试{DB_CONNECT_MAX_RETRIES}次）"
        raise DbConnectError(f"{err_msg}... e:{last_error}") from last_error
