import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import PokeNotifyEvent
from nonebot.matcher import Matcher
from nonebot.message import run_postprocessor
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.config import Config
from liuying.models.plugin_info import PluginInfo
from liuying.models.statistics import Statistics
from liuying.utils.enum import PluginType
from liuying.utils.log import logger

Config.add_plugin_config(
    "hook",
    "STATISTICS_ENABLE",
    True,
    help="是否启用功能调用统计",
    default_value=True,
    type=bool,
)

Config.add_plugin_config(
    "hook",
    "STATISTICS_BATCH_INTERVAL",
    60,
    help="批量写入统计数据的间隔（秒）",
    default_value=60,
    type=int,
)

Config.add_plugin_config(
    "hook",
    "STATISTICS_BATCH_SIZE",
    100,
    help="批量写入统计数据的最大数量",
    default_value=100,
    type=int,
)

LOG_COMMAND = "StatisticsHook"


@dataclass(slots=True)
class StatisticsRecord:
    """统计记录数据"""

    user_id: str
    group_id: str | None
    plugin_name: str
    create_time: datetime
    bot_id: str


class StatisticsQueue:
    """统计队列，用于异步批量写入"""

    _queue: ClassVar[asyncio.Queue[StatisticsRecord]] = asyncio.Queue()
    _task: ClassVar[asyncio.Task | None] = None
    _running: ClassVar[bool] = False

    @classmethod
    async def start(cls):
        """启动统计队列处理。"""
        if cls._running:
            return
        cls._running = True
        cls._task = asyncio.create_task(cls._process_queue())

    @classmethod
    async def stop(cls):
        """停止统计队列处理。"""
        cls._running = False
        if cls._task:
            cls._task.cancel()
            with suppress(asyncio.CancelledError):
                await cls._task
            cls._task = None

    @classmethod
    def add(cls, record: StatisticsRecord):
        """添加统计记录到队列。

        参数:
            record: 统计记录
        """
        try:
            cls._queue.put_nowait(record)
        except asyncio.QueueFull:
            logger.warning("统计队列已满，丢弃记录", LOG_COMMAND)

    @classmethod
    async def _process_queue(cls):
        """处理统计队列。"""
        batch_interval = Config.get_config("hook", "STATISTICS_BATCH_INTERVAL") or 60
        batch_size = Config.get_config("hook", "STATISTICS_BATCH_SIZE") or 100

        while cls._running:
            records: list[StatisticsRecord] = []
            try:
                await asyncio.sleep(batch_interval)
                while not cls._queue.empty() and len(records) < batch_size:
                    record = cls._queue.get_nowait()
                    records.append(record)

                if records:
                    await cls._write_records(records)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("处理统计队列失败", LOG_COMMAND, e=e)

    @classmethod
    async def _write_records(cls, records: list[StatisticsRecord]):
        """批量写入统计记录。

        参数:
            records: 统计记录列表
        """
        try:
            statistics_list = [
                Statistics(
                    user_id=r.user_id,
                    group_id=r.group_id,
                    plugin_name=r.plugin_name,
                    create_time=r.create_time,
                    bot_id=r.bot_id,
                )
                for r in records
            ]
            await Statistics.filter().bulk_create(statistics_list)
            logger.debug(f"批量添加调用记录 {len(records)} 条", LOG_COMMAND)
        except Exception as e:
            logger.error("批量写入统计记录失败", LOG_COMMAND, e=e)


@run_postprocessor
async def _(
    matcher: Matcher,
    exception: Exception | None,
    bot: Bot,
    uninfo: Uninfo,
    event: Event,
):
    """记录插件调用。"""
    if not Config.get_config("hook", "STATISTICS_ENABLE"):
        return

    if matcher.type == "notice" and not isinstance(event, PokeNotifyEvent):
        return

    if not (uninfo.user.id and matcher.plugin):
        return

    plugin = await PluginInfo.get_plugin(module_path=matcher.plugin.module_name)
    if not plugin or plugin.plugin_type != PluginType.NORMAL:
        return

    group_id = None
    if uninfo.group:
        group_id = (
            uninfo.group.parent.id if uninfo.group.parent else uninfo.group.id
        )

    logger.debug(f"提交调用记录: {matcher.plugin_name}...", LOG_COMMAND)

    StatisticsQueue.add(
        StatisticsRecord(
            user_id=uninfo.user.id,
            group_id=group_id,
            plugin_name=matcher.plugin_name,
            create_time=datetime.now(),
            bot_id=bot.self_id,
        )
    )
