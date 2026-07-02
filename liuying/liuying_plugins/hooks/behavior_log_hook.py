import asyncio
from contextlib import suppress
import time
from typing import ClassVar

from nonebot.adapters import Bot, Event
from nonebot.matcher import Matcher
from nonebot.message import run_postprocessor, run_preprocessor
from nonebot.typing import T_State
from nonebot_plugin_alconna import UniMsg
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.config import Config
from liuying.models._log.behavior_log import BehaviorLog
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.platform import PlatformUtils

from .auth.utils import get_group_channel_ids

Config.add_plugin_config(
    "hook",
    "BEHAVIOR_LOG_ENABLE",
    True,
    help="是否启用用户行为日志",
    default_value=True,
    type=bool,
)

Config.add_plugin_config(
    "hook",
    "BEHAVIOR_LOG_TO_DB",
    False,
    help="是否记录行为日志到数据库",
    default_value=False,
    type=bool,
)

Config.add_plugin_config(
    "hook",
    "BEHAVIOR_LOG_RAW_MESSAGE",
    False,
    help="是否记录原始消息内容",
    default_value=False,
    type=bool,
)

Config.add_plugin_config(
    "hook",
    "BEHAVIOR_LOG_IGNORE_MODULES",
    [],
    help="不记录日志的模块列表",
    default_value=[],
    type=list,
)

LOG_COMMAND = "BehaviorHook"

_STATE_KEY = "_behavior_logged"
_IGNORED_KEY = "_behavior_ignored"


class BehaviorLogQueue:
    """行为日志队列，用于异步批量写入"""

    _queue: ClassVar[asyncio.Queue] = asyncio.Queue()
    _task: ClassVar[asyncio.Task | None] = None
    _running: ClassVar[bool] = False
    _batch_size: ClassVar[int] = 50
    _flush_interval: ClassVar[float] = 5.0

    @classmethod
    async def start(cls):
        """启动日志队列处理"""
        if cls._running:
            return
        cls._running = True
        cls._task = asyncio.create_task(cls._process_queue())

    @classmethod
    async def stop(cls):
        """停止日志队列处理"""
        cls._running = False
        if cls._task:
            cls._task.cancel()
            with suppress(asyncio.CancelledError):
                await cls._task
            cls._task = None

    @classmethod
    def add(cls, log_data: dict):
        """添加日志到队列

        参数:
            log_data: 日志数据
        """
        try:
            cls._queue.put_nowait(log_data)
        except asyncio.QueueFull:
            logger.warning("行为日志队列已满，丢弃日志", LOG_COMMAND)

    @classmethod
    async def _process_queue(cls):
        """处理日志队列"""
        while cls._running:
            logs = []
            try:
                await asyncio.sleep(cls._flush_interval)
                while not cls._queue.empty() and len(logs) < cls._batch_size:
                    log_data = cls._queue.get_nowait()
                    logs.append(log_data)

                if logs:
                    await cls._write_logs(logs)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("处理行为日志队列失败", LOG_COMMAND, e=e)

    @classmethod
    async def _write_logs(cls, logs: list[dict]):
        """批量写入日志

        参数:
            logs: 日志列表
        """
        for log_data in logs:
            with suppress(Exception):
                await BehaviorLog.add_log(**log_data)


@run_preprocessor
async def _(
    matcher: Matcher,
    bot: Bot,
    event: Event,
    state: T_State,
    session: Uninfo,
    message: UniMsg,
):
    """用户行为日志预处理"""
    if not Config.get_config("hook", "BEHAVIOR_LOG_ENABLE"):
        return

    if plugin := matcher.plugin:
        if metadata := plugin.metadata:
            extra = metadata.extra
            if extra.get("plugin_type") in {
                PluginType.HIDDEN,
                PluginType.DEPENDANT,
            }:
                state[_IGNORED_KEY] = True
                return

    ignore_modules = Config.get_config("hook", "BEHAVIOR_LOG_IGNORE_MODULES") or []
    module = matcher.plugin_name or ""
    if module in ignore_modules:
        state[_IGNORED_KEY] = True
        return

    state[_STATE_KEY] = {
        "module": module,
        "command": message.extract_plain_text()[:500] if message else None,
        "raw_message": str(message)[:5000] if message else None,
        "start_time": time.time(),
    }


@run_postprocessor
async def _(
    matcher: Matcher,
    exception: Exception | None,
    bot: Bot,
    event: Event,
    session: Uninfo,
    state: T_State,
):
    """用户行为日志后处理"""
    if not Config.get_config("hook", "BEHAVIOR_LOG_ENABLE"):
        return

    if state.get(_IGNORED_KEY):
        return

    log_data = state.get(_STATE_KEY)
    if not log_data:
        return

    module = log_data["module"]
    if not module:
        return

    ids = get_group_channel_ids(session)
    user_id = session.user.id

    status = 0
    error_msg = None
    if exception:
        status = 1
        error_msg = str(exception)[:500]

    log_to_db = Config.get_config("hook", "BEHAVIOR_LOG_TO_DB")
    log_raw = Config.get_config("hook", "BEHAVIOR_LOG_RAW_MESSAGE")

    logger.debug(
        f"用户行为: {module}, 用户: {user_id}, 群组: {ids.group_id}, 状态: {status}",
        LOG_COMMAND,
        session=session,
    )

    if log_to_db:
        BehaviorLogQueue.add({
            "user_id": user_id,
            "module": module,
            "group_id": ids.group_id,
            "channel_id": ids.channel_id,
            "command": log_data.get("command"),
            "raw_message": log_data.get("raw_message") if log_raw else None,
            "status": status,
            "error_msg": error_msg,
            "platform": PlatformUtils.get_platform(session),
            "bot_id": bot.self_id,
        })
