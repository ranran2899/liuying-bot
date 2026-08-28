"""功能调用统计钩子"""

from dataclasses import dataclass
from datetime import datetime

from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import PokeNotifyEvent
from nonebot.matcher import Matcher
from nonebot.message import run_postprocessor
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.config import Config
from liuying.models.plugin_info import PluginInfo
from liuying.models.statistics import Statistics
from liuying.services.data_access import DataAccess
from liuying.utils.batch_queue import BatchQueue
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.manager import PriorityLifecycle

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


async def _write_records(records: list[StatisticsRecord]) -> None:
    """批量写入统计记录

    参数:
        records: 统计记录列表
    """
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
    await Statistics.bulk_add(statistics_list)
    logger.debug(f"批量添加调用记录 {len(records)} 条", LOG_COMMAND)


_batch_queue = BatchQueue[StatisticsRecord]("统计", _write_records)


@PriorityLifecycle.on_startup(priority=10)
async def _start_statistics_queue():
    """启动统计队列处理"""
    await _batch_queue.start(
        Config.get_config("hook", "STATISTICS_BATCH_INTERVAL") or 60,
        Config.get_config("hook", "STATISTICS_BATCH_SIZE") or 100,
    )


@PriorityLifecycle.on_shutdown(priority=10)
async def _stop_statistics_queue():
    """停止统计队列处理"""
    await _batch_queue.stop()


@run_postprocessor
async def _(
    matcher: Matcher,
    exception: Exception | None,
    bot: Bot,
    uninfo: Uninfo,
    event: Event,
):
    """记录插件调用"""
    if not Config.get_config("hook", "STATISTICS_ENABLE"):
        return

    if matcher.type == "notice" and not isinstance(event, PokeNotifyEvent):
        return

    if not (uninfo.user.id and matcher.plugin):
        return

    # 经 DataAccess 按 module 查询命中插件缓存，避免每次调用穿透数据库
    plugin = await DataAccess(PluginInfo).safe_get_or_none(
        module=matcher.plugin_name or ""
    )
    if not plugin or plugin.plugin_type != PluginType.NORMAL:
        return

    group_id = None
    if uninfo.group:
        group_id = (
            uninfo.group.parent.id if uninfo.group.parent else uninfo.group.id
        )

    logger.debug(f"提交调用记录: {matcher.plugin_name}...", LOG_COMMAND)

    _batch_queue.add(
        StatisticsRecord(
            user_id=uninfo.user.id,
            group_id=group_id,
            plugin_name=matcher.plugin_name,
            create_time=datetime.now(),
            bot_id=bot.self_id,
        )
    )
