from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.config import BotConfig
from liuying.configs.utils import PluginExtraData
from liuying.services.liuying_db import session_manager
from liuying.services.log import logger
from liuying.utils.enum import PluginType
from liuying.utils.image import ImageTemplate
from liuying.utils.message import MessageUtils

DANGEROUS_KEYWORDS = {"drop", "delete", "truncate", "alter", "update", "insert"}

MAX_RESULT_ROWS = 200

__plugin_meta__ = PluginMetadata(
    name="数据库操作",
    description="执行sql语句与查看表",
    usage="""
    查看所有表
    查看数据库表 [数据库名称]
    exec [sql语句]
    exec -f [sql语句]  : 跳过二次确认直接执行
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.2",
        plugin_type=PluginType.SUPERUSER,
    ).to_dict(),
)

_matcher = on_alconna(
    Alconna("exec", Args["sql_text", str]),
    permission=SUPERUSER,
    priority=1,
    block=True,
)

_table_matcher = on_alconna(
    Alconna("查看所有表"),
    permission=SUPERUSER,
    priority=1,
    block=True,
)

_db_table_matcher = on_alconna(
    Alconna("查看数据库表", Args["db_name", str]),
    permission=SUPERUSER,
    priority=1,
    block=True,
)

SELECT_TABLE_MYSQL_SQL = """
SELECT table_name AS name, table_comment AS `desc`
FROM information_schema.tables
WHERE table_schema = DATABASE();
"""

SELECT_TABLE_SQLITE_SQL = """
SELECT name FROM sqlite_master WHERE type='table';
"""

SELECT_TABLE_PSQL_SQL = """
select a.tablename as name,d.description as desc from pg_tables a
    left join pg_class c on relname=tablename
    left join pg_description d on oid=objoid and objsubid=0
    where a.schemaname = 'public'
"""

type2sql = {
    "mysql": SELECT_TABLE_MYSQL_SQL,
    "sqlite": SELECT_TABLE_SQLITE_SQL,
    "postgres": SELECT_TABLE_PSQL_SQL,
}

MYSQL_DB_TABLES_SQL = """
SELECT table_name AS name, table_comment AS `desc`
FROM information_schema.tables
WHERE table_schema = :db_name;
"""

PSQL_DB_TABLES_SQL = """
SELECT a.tablename AS name, d.description AS `desc`
FROM pg_tables a
LEFT JOIN pg_class c ON relname = tablename
LEFT JOIN pg_description d ON oid = objoid AND objsubid = 0
WHERE a.schemaname = :db_name
"""

_confirm_pending: dict[str, str] = {}


def _is_dangerous_sql(sql_text: str) -> bool:
    """判断SQL语句是否为危险操作

    参数:
        sql_text: SQL语句文本

    返回:
        bool: 是否为危险操作
    """
    first_word = sql_text.strip().lower().split()[0] if sql_text.strip() else ""
    return first_word in DANGEROUS_KEYWORDS


def _parse_sql_type(sql_type: str) -> str:
    """解析数据库类型

    参数:
        sql_type: 原始数据库类型字符串

    返回:
        str: 实际的数据库类型
    """
    if "+" in sql_type:
        sql_type = sql_type.split("+")[0]
    return sql_type


@_matcher.handle()
async def _(session: Uninfo, sql_text: str):
    """执行SQL语句

    参数:
        session: 会话信息
        sql_text: SQL语句文本
    """
    sql_text = sql_text.strip()
    if sql_text.startswith("exec"):
        sql_text = sql_text[4:].strip()
    if not sql_text:
        await MessageUtils.build_message("需要执行的SQL语句!").finish()

    force = False
    if sql_text.startswith("-f "):
        force = True
        sql_text = sql_text[3:].strip()

    user_id = session.user.id

    if not force and _is_dangerous_sql(sql_text):
        if user_id in _confirm_pending and _confirm_pending[user_id] == sql_text:
            del _confirm_pending[user_id]
        else:
            _confirm_pending[user_id] = sql_text
            logger.warning(f"危险SQL待确认: {sql_text[:100]}", "exec", session=session)
            await MessageUtils.build_message(
                "检测到危险操作，请再次发送相同命令以确认执行!\n"
                f"SQL: {sql_text[:200]}"
            ).finish()

    logger.info(f"执行SQL语句: {sql_text[:200]}", "exec", session=session)

    try:
        async with session_manager.get_session() as db_session:
            from sqlalchemy import text

            if sql_text.lower().startswith("select"):
                result = await db_session.execute(text(sql_text))
                rows = result.fetchall()

                if not rows:
                    await MessageUtils.build_message("查询结果为空!").send()
                    return

                columns = list(result.keys())
                display_rows = rows[:MAX_RESULT_ROWS]
                data_list = [list(row) for row in display_rows]

                total_msg = f"总共有 {len(rows)} 条数据"
                if len(rows) > MAX_RESULT_ROWS:
                    total_msg += f"，显示前 {MAX_RESULT_ROWS} 条"
                table = await ImageTemplate.table_page(
                    "EXEC",
                    total_msg,
                    columns,
                    data_list,
                )
                await MessageUtils.build_message(table).send()
            else:
                result = await db_session.execute(text(sql_text))
                await db_session.commit()
                rowcount = result.rowcount
                await MessageUtils.build_message(
                    f"执行SQL语句成功! 影响行数: {rowcount}"
                ).send()

    except Exception as e:
        logger.error("执行 SQL 语句失败...", session=session, e=e)
        await MessageUtils.build_message(
            f"执行 SQL 语句失败... {type(e).__name__}: {e}"
        ).finish()


@_table_matcher.handle()
async def _(session: Uninfo):
    """查看默认数据库所有表

    参数:
        session: 会话信息
    """
    try:
        async with session_manager.get_session() as db_session:
            from sqlalchemy import text

            sql_type = _parse_sql_type(BotConfig.get_sql_type())
            select_sql = type2sql.get(sql_type)

            if not select_sql:
                await MessageUtils.build_message(
                    f"不支持的数据库类型: {sql_type}"
                ).send()
                return

            result = await db_session.execute(text(select_sql))
            rows = result.fetchall()

            column_name = ["表名", "简介"]
            data_list = []

            for row in rows:
                if len(row) == 1:
                    data_list.append([row[0], ""])
                else:
                    data_list.append([row[0], row[1] if row[1] else ""])

            logger.info("查看数据库所有表", "查看所有表", session=session)

            table = await ImageTemplate.table_page(
                "数据库表", f"总共有 {len(data_list)} 张表", column_name, data_list
            )
            await MessageUtils.build_message(table).send()

    except Exception as e:
        logger.error("获取表数据失败...", session=session, e=e)
        await MessageUtils.build_message(
            f"获取表数据失败... {type(e).__name__}: {e}"
        ).send()


@_db_table_matcher.handle()
async def _(session: Uninfo, db_name: str):
    """查看指定数据库的全部表

    参数:
        session: 会话信息
        db_name: 数据库名称
    """
    try:
        async with session_manager.get_session() as db_session:
            from sqlalchemy import text

            sql_type = _parse_sql_type(BotConfig.get_sql_type())

            match sql_type:
                case "mysql":
                    result = await db_session.execute(
                        text(MYSQL_DB_TABLES_SQL), {"db_name": db_name}
                    )
                case "postgres":
                    result = await db_session.execute(
                        text(PSQL_DB_TABLES_SQL), {"db_name": db_name}
                    )
                case "sqlite":
                    await MessageUtils.build_message(
                        "SQLite 为单文件数据库，不支持查看其他数据库，请使用 查看所有表"
                    ).finish()
                case _:
                    await MessageUtils.build_message(
                        f"不支持的数据库类型: {sql_type}"
                    ).send()
                    return

            rows = result.fetchall()

            if not rows:
                await MessageUtils.build_message(
                    f"数据库 {db_name} 中没有表或数据库不存在"
                ).finish()

            column_name = ["表名", "简介"]
            data_list = []

            for row in rows:
                if len(row) == 1:
                    data_list.append([row[0], ""])
                else:
                    data_list.append([row[0], row[1] if row[1] else ""])

            logger.info(f"查看数据库 {db_name} 所有表", "查看数据库表", session=session)

            table = await ImageTemplate.table_page(
                f"数据库: {db_name}",
                f"总共有 {len(data_list)} 张表",
                column_name,
                data_list,
            )
            await MessageUtils.build_message(table).send()

    except Exception as e:
        logger.error(f"获取数据库 {db_name} 表数据失败...", session=session, e=e)
        await MessageUtils.build_message(
            f"获取数据库表数据失败... {type(e).__name__}: {e}"
        ).send()
