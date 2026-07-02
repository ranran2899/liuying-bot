"""数据库工具模块

提供数据库操作超时控制、模型元数据辅助与日期范围生成等工具能力，
统一封装在 ``DbUtils`` 类中，避免散装函数导入。
"""

import asyncio
from datetime import datetime, timedelta
import time
from typing import Any

from sqlalchemy import inspect

from liuying.utils.log import logger

from .config import DB_TIMEOUT_SECONDS, LOG_COMMAND, SLOW_QUERY_THRESHOLD

_MIDNIGHT: dict = {"hour": 0, "minute": 0, "second": 0, "microsecond": 0}
_END_OF_DAY: dict = {"hour": 23, "minute": 59, "second": 59, "microsecond": 999999}


class DbUtils:
    """数据库工具集合

    封装数据库操作超时控制、模型列元数据查询与日期范围生成等静态工具方法,
    供 ``base_model``、``query`` 子包与 ``lifecycle`` 等模块统一调用。
    """

    @staticmethod
    async def with_db_timeout(
        coro: Any,
        timeout_seconds: float = DB_TIMEOUT_SECONDS,
        operation: str | None = None,
        source: str | None = None,
    ) -> Any:
        """带超时控制的数据库操作

        参数:
            coro: 协程对象
            timeout_seconds: 超时时间（秒）
            operation: 操作名称
            source: 来源

        返回:
            协程执行结果

        异常:
            asyncio.TimeoutError: 超时异常
        """
        start_time = time.perf_counter()
        try:
            async with asyncio.timeout(timeout_seconds):
                result = await coro
            elapsed = time.perf_counter() - start_time
            if elapsed > SLOW_QUERY_THRESHOLD and operation:
                logger.warning(f"慢查询: {operation} 耗时 {elapsed:.3f}s", LOG_COMMAND)
            return result
        except TimeoutError:
            if operation:
                logger.error(
                    f"数据库操作超时: {operation} (>{timeout_seconds}s) "
                    f"来源: {source}",
                    LOG_COMMAND,
                )
            raise

    @staticmethod
    def get_column(model_class: Any, column: str | Any) -> Any:
        """获取列对象，支持字符串和列对象

        参数:
            model_class: 模型类
            column: 列名（字符串）或列对象

        返回:
            Any: 列对象
        """
        return (
            getattr(model_class, column) if isinstance(column, str) else column
        )

    @staticmethod
    def get_primary_key_names(model_class: Any) -> tuple[str, ...]:
        """获取模型的主键列名

        参数:
            model_class: 模型类

        返回:
            tuple[str, ...]: 主键列名元组
        """
        return tuple(col.name for col in inspect(model_class).primary_key)

    @staticmethod
    def get_date_range(
        period: str,
        base_date: datetime | None = None,
    ) -> tuple[datetime, datetime]:
        """获取指定时间范围的起止时间

        参数:
            period: 时间周期，支持 'today', 'yesterday', 'this_week',
                    'last_week', 'this_month', 'last_month', 'this_year',
                    'last_year'
            base_date: 基准日期，默认为当前时间

        返回:
            tuple[datetime, datetime]: (起始时间, 结束时间)
        """
        if base_date is None:
            base_date = datetime.today()

        today_start = base_date.replace(**_MIDNIGHT)
        today_end = base_date.replace(**_END_OF_DAY)

        match period:
            case "today":
                return today_start, today_end
            case "yesterday":
                yesterday = base_date - timedelta(days=1)
                return (
                    yesterday.replace(**_MIDNIGHT),
                    yesterday.replace(**_END_OF_DAY),
                )
            case "this_week":
                week_start = today_start - timedelta(days=base_date.weekday())
                week_end = week_start + timedelta(
                    days=6,
                    hours=23,
                    minutes=59,
                    seconds=59,
                    microseconds=999999,
                )
                return week_start, week_end
            case "last_week":
                week_start = today_start - timedelta(days=base_date.weekday())
                last_week_end = week_start - timedelta(seconds=1)
                last_week_start = week_start - timedelta(weeks=1)
                return last_week_start, last_week_end
            case "this_month":
                month_start = base_date.replace(day=1, **_MIDNIGHT)
                next_month = (
                    base_date.replace(year=base_date.year + 1, month=1, day=1)
                    if base_date.month == 12
                    else base_date.replace(month=base_date.month + 1, day=1)
                )
                return month_start, next_month - timedelta(seconds=1)
            case "last_month":
                month_start = base_date.replace(day=1, **_MIDNIGHT)
                last_month_start = (
                    month_start.replace(year=base_date.year - 1, month=12)
                    if base_date.month == 1
                    else month_start.replace(month=base_date.month - 1)
                )
                return last_month_start, month_start - timedelta(seconds=1)
            case "this_year":
                return (
                    base_date.replace(month=1, day=1, **_MIDNIGHT),
                    base_date.replace(month=12, day=31, **_END_OF_DAY),
                )
            case "last_year":
                return (
                    base_date.replace(
                        year=base_date.year - 1, month=1, day=1, **_MIDNIGHT
                    ),
                    base_date.replace(
                        year=base_date.year - 1,
                        month=12,
                        day=31,
                        **_END_OF_DAY,
                    ),
                )
            case _:
                raise ValueError(f"不支持的时间周期: {period}")
