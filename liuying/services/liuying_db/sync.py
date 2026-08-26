"""数据库同步模块，负责将主数据库的数据同步到副数据库"""

import asyncio
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    MetaData,
    Table,
    delete,
    inspect,
    select,
)
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from liuying.utils.log import logger

from .config import LOG_COMMAND

_SYNC_MAX_RETRIES = 3
_SYNC_RETRY_DELAY = 5.0

_TIME_FORMATS = ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d")


class DBSyncManager:
    """数据库同步管理器，负责管理主从数据库的同步任务"""

    __slots__ = ("last_sync_time", "sync_errors", "sync_tasks")

    def __init__(self):
        self.sync_tasks: dict[str, asyncio.Task] = {}
        self.last_sync_time: dict[str, float] = {}
        self.sync_errors: dict[str, int] = {}

    async def sync_database(self, slave_db_name: str):
        """同步单个副数据库，包含重试机制

        参数:
            slave_db_name: 副数据库名称
        """
        for attempt in range(_SYNC_MAX_RETRIES):
            try:
                await self._do_sync(slave_db_name)
                self.sync_errors.pop(slave_db_name, None)
                return
            except Exception as e:
                err_count = self.sync_errors.get(slave_db_name, 0) + 1
                self.sync_errors[slave_db_name] = err_count
                if attempt < _SYNC_MAX_RETRIES - 1:
                    delay = _SYNC_RETRY_DELAY * (2**attempt)
                    logger.warning(
                        f"同步副数据库 {slave_db_name} 失败 (第{attempt + 1}次)，"
                        f"{delay}秒后重试: {e}",
                        LOG_COMMAND,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"同步副数据库 {slave_db_name} 失败，已重试"
                        f"{_SYNC_MAX_RETRIES}次: {e}",
                        LOG_COMMAND,
                    )

    def _reflect_table(self, sync_conn, tbl_name: str) -> Table:
        """从数据库反射表结构，获取包含列类型信息的 Table 对象

        参数:
            sync_conn: 同步数据库连接
            tbl_name: 表名

        返回:
            Table: 包含完整列定义的表对象
        """
        metadata = MetaData()
        return Table(tbl_name, metadata, autoload_with=sync_conn)

    async def _get_table_names(self, conn: AsyncConnection) -> list[str]:
        """获取数据库中的所有表名

        参数:
            conn: 数据库连接

        返回:
            list[str]: 表名列表
        """
        return await conn.run_sync(lambda c: inspect(c).get_table_names())

    async def _get_primary_key(
        self,
        conn: AsyncConnection,
        table_name: str,
    ) -> str | None:
        """获取表的主键列名

        参数:
            conn: 数据库连接
            table_name: 表名

        返回:
            str | None: 主键列名，如果没有主键则返回None
        """

        def _inspect_pk(sync_conn, tbl_name):
            pk = inspect(sync_conn).get_pk_constraint(tbl_name)
            return pk["constrained_columns"][0] if pk["constrained_columns"] else None

        return await conn.run_sync(_inspect_pk, table_name)

    async def _fetch_max_pk(
        self,
        session: AsyncSession,
        tbl: Any,
        pk_col: Any,
    ) -> Any:
        """获取指定表的主键最大值

        参数:
            session: 数据库会话
            tbl: 表对象
            pk_col: 主键列对象

        返回:
            Any: 主键最大值
        """
        result = await session.execute(select(pk_col).order_by(pk_col.desc()).limit(1))
        return result.scalar()

    @staticmethod
    def _convert_time_fields(
        row: dict[str, Any], tbl: Any
    ) -> dict[str, Any]:
        """仅对日期/时间类型的列，将字符串值解析为对应对象

        基于表 metadata 列类型精准转换，避免对每行每列盲目尝试多种时间格式，
        也避免误转非时间字段中的日期文本。非字符串或无法解析的值原样保留。

        参数:
            row: 原始数据行
            tbl: 表对象（含列类型信息）

        返回:
            dict: 转换后的数据行
        """
        converted = {}
        for key, value in row.items():
            col_type = tbl.c[key].type if key in tbl.c else None
            if isinstance(value, str) and isinstance(col_type, (DateTime, Date)):
                for fmt in _TIME_FORMATS:
                    try:
                        parsed = datetime.strptime(value, fmt)
                        value = parsed.date() if isinstance(col_type, Date) else parsed
                        break
                    except (ValueError, TypeError):
                        continue
            converted[key] = value
        return converted

    async def _sync_table(
        self,
        master_session,
        slave_session,
        master_conn,
        tbl_name,
        slave_db_name,
    ):
        """同步单个表

        有主键的表采用「按最大主键增量同步」策略，前提是主从库主键单调递增且
        连续（副库不应被外部直接修改、主库删除行后主键不重用）。该假设不成立
        时（如人工改从库、主键缺口）可能导致数据不一致，此时应改用全量同步或
        基于 ``updated_at`` 的 CDC 方案。

        参数:
            master_session: 主数据库会话
            slave_session: 副数据库会话
            master_conn: 主数据库连接
            tbl_name: 表名
            slave_db_name: 副数据库名称
        """
        pk = await self._get_primary_key(master_conn, tbl_name)
        # 反射表结构以获取列类型信息，用于时间字段转换
        tbl = await master_conn.run_sync(self._reflect_table, tbl_name)

        if not pk:
            logger.debug(f"表 {tbl_name} 没有主键，执行全量同步", LOG_COMMAND)
            await slave_session.execute(delete(tbl))
            result = await master_session.execute(select(tbl))
            rows = result.mappings().all()
        else:
            pk_col = tbl.c[pk]
            slave_max_pk = await self._fetch_max_pk(slave_session, tbl, pk_col)
            master_max_pk = await self._fetch_max_pk(master_session, tbl, pk_col)

            match (slave_max_pk, master_max_pk):
                case (None, _):
                    result = await master_session.execute(select(tbl))
                    rows = result.mappings().all()
                case (_, None):
                    await slave_session.execute(delete(tbl))
                    rows = []
                case (s_max, m_max) if m_max < s_max:
                    logger.warning(
                        f"主数据库表 {tbl_name} 的最大主键值 {m_max} "
                        f"小于副数据库 {slave_db_name} 的值 {s_max}，执行全量同步",
                        LOG_COMMAND,
                    )
                    await slave_session.execute(delete(tbl))
                    result = await master_session.execute(select(tbl))
                    rows = result.mappings().all()
                case _:
                    result = await master_session.execute(
                        select(tbl).where(pk_col > slave_max_pk)
                    )
                    rows = result.mappings().all()

        if not rows:
            logger.debug(f"表 {tbl_name} 没有新增数据，跳过同步", LOG_COMMAND)
            return

        rows_to_insert = [self._convert_time_fields(dict(row), tbl) for row in rows]
        insert_stmt = tbl.insert().values(rows_to_insert)
        await slave_session.execute(insert_stmt)

        sync_type = "同步" if pk else "全量同步"
        logger.debug(
            f"表 {tbl_name} {sync_type}完成，共插入 {len(rows)} 条数据",
            LOG_COMMAND,
        )

    async def _do_sync(self, slave_db_name: str):
        """执行实际的同步操作

        参数:
            slave_db_name: 副数据库名称
        """
        logger.info(f"开始同步副数据库 {slave_db_name}...", LOG_COMMAND)

        # 循环依赖：session 导入 sync_manager，sync 按需导入 session_manager
        from .session import session_manager

        async with (
            session_manager.get_session() as master_session,
            session_manager.get_session(slave_db_name) as slave_session,
        ):
            master_conn = await master_session.connection()
            tables = await self._get_table_names(master_conn)

            for tbl_name in tables:
                logger.debug(
                    f"开始同步表 {tbl_name} 到副数据库 {slave_db_name}...",
                    LOG_COMMAND,
                )
                await self._sync_table(
                    master_session,
                    slave_session,
                    master_conn,
                    tbl_name,
                    slave_db_name,
                )

            await slave_session.flush()
            self.last_sync_time[slave_db_name] = asyncio.get_running_loop().time()
            logger.info(f"副数据库 {slave_db_name} 同步完成", LOG_COMMAND)

    def get_sync_status(self) -> dict[str, Any]:
        """获取同步状态信息

        返回:
            dict: 包含各副数据库同步状态的字典
        """
        return {
            "last_sync_time": {
                k: datetime.fromtimestamp(v).isoformat()
                for k, v in self.last_sync_time.items()
            },
            "sync_errors": dict(self.sync_errors),
            "active_tasks": list(self.sync_tasks.keys()),
        }

    async def start_sync(self, slave_db_names: list[str], interval: int = 3600):
        """启动同步任务

        参数:
            slave_db_names: 需要同步的副数据库名称列表
            interval: 同步间隔，单位为秒，默认1小时
        """
        logger.info(
            f"启动数据库同步任务，同步副数据库: {slave_db_names}，间隔: {interval}秒",
            LOG_COMMAND,
        )

        async def sync_loop(slave_db_name: str):
            while True:
                await self.sync_database(slave_db_name)
                await asyncio.sleep(interval)

        for db_name in slave_db_names:
            if db_name not in self.sync_tasks:
                self.sync_tasks[db_name] = asyncio.create_task(sync_loop(db_name))

    async def stop_sync(self):
        """停止所有同步任务"""
        logger.info("停止所有数据库同步任务...", LOG_COMMAND)
        for task in self.sync_tasks.values():
            task.cancel()
        await asyncio.gather(*self.sync_tasks.values(), return_exceptions=True)
        self.sync_tasks.clear()
        logger.info("所有数据库同步任务已停止", LOG_COMMAND)


sync_manager = DBSyncManager()
