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
    db_model,
    get_config,
    prompt,
)
from .exceptions import DbConnectError, DbUrlIsNone
from .session import session_manager
from .sync import sync_manager
from .utils import DbUtils

driver = nonebot.get_driver()


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
                        scripts_by_db.setdefault(db_name, []).extend(sql)
                except Exception as e:
                    logger.debug(
                        f"{module} 在数据库 {db_name} 执行脚本方法出错...", e=e
                    )

        for db_name, sql_list in scripts_by_db.items():
            async with session_manager.get_session(db_name) as session:
                for sql in sql_list:
                    logger.debug(f"执行SQL: {sql}")
                    try:
                        await DbUtils.with_db_timeout(
                            session.execute(text(sql)),
                            operation=f"执行SQL: {sql[:50]}...",
                        )
                        await session.commit()
                    except Exception as e:
                        logger.debug(f"执行SQL: {sql} 错误...", e=e)
                        await session.rollback()

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


