"""聊天记录钩子"""

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from nonebot import on_message
from nonebot.adapters import Event
from nonebot_plugin_alconna import UniMsg
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.config import Config
from liuying.models.chat_history import ChatHistory
from liuying.utils.log import logger
from liuying.utils.manager import PriorityLifecycle

Config.add_plugin_config(
    "hook",
    "CHAT_HISTORY_ENABLE",
    True,
    help="是否启用聊天记录",
    default_value=True,
    type=bool,
)

Config.add_plugin_config(
    "hook",
    "CHAT_HISTORY_BATCH_INTERVAL",
    60,
    help="批量写入聊天记录的间隔（秒）",
    default_value=60,
    type=int,
)

Config.add_plugin_config(
    "hook",
    "CHAT_HISTORY_BATCH_SIZE",
    100,
    help="批量写入聊天记录的最大数量",
    default_value=100,
    type=int,
)

LOG_COMMAND = "ChatHistoryHook"

_MESSAGE_MAX_LENGTH = 5000


@dataclass(slots=True)
class ChatHistoryRecord:
    """聊天记录数据"""

    user_id: str | None
    group_id: str | None
    bot_id: str
    message: str | None
    create_time: datetime


class ChatHistoryQueue:
    """聊天记录队列，用于异步批量写入"""

    _queue: ClassVar[asyncio.Queue[ChatHistoryRecord]] = asyncio.Queue()
    _task: ClassVar[asyncio.Task | None] = None
    _running: ClassVar[bool] = False

    @classmethod
    async def start(cls):
        """启动聊天记录队列处理。"""
        if cls._running:
            return
        cls._running = True
        cls._task = asyncio.create_task(cls._process_queue())

    @classmethod
    async def stop(cls):
        """停止聊天记录队列处理并刷写剩余记录。"""
        cls._running = False
        if cls._task:
            cls._task.cancel()
            with suppress(asyncio.CancelledError):
                await cls._task
            cls._task = None
        await cls._flush_remaining()

    @classmethod
    async def _flush_remaining(cls):
        """刷写队列中剩余的记录。"""
        records: list[ChatHistoryRecord] = []
        while not cls._queue.empty():
            records.append(cls._queue.get_nowait())
        if records:
            await cls._write_records(records)

    @classmethod
    def add(cls, record: ChatHistoryRecord):
        """添加聊天记录到队列。

        参数:
            record: 聊天记录
        """
        try:
            cls._queue.put_nowait(record)
        except asyncio.QueueFull:
            logger.warning("聊天记录队列已满，丢弃记录", LOG_COMMAND)

    @classmethod
    async def _process_queue(cls):
        """处理聊天记录队列。"""
        batch_interval = Config.get_config("hook", "CHAT_HISTORY_BATCH_INTERVAL") or 60
        batch_size = Config.get_config("hook", "CHAT_HISTORY_BATCH_SIZE") or 100

        while cls._running:
            records: list[ChatHistoryRecord] = []
            try:
                await asyncio.sleep(batch_interval)
                while not cls._queue.empty() and len(records) < batch_size:
                    records.append(cls._queue.get_nowait())

                if records:
                    await cls._write_records(records)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("处理聊天记录队列失败", LOG_COMMAND, e=e)

    @classmethod
    async def _write_records(cls, records: list[ChatHistoryRecord]):
        """批量写入聊天记录。

        参数:
            records: 聊天记录列表
        """
        try:
            history_list = [
                ChatHistory(
                    user_id=r.user_id,
                    group_id=r.group_id,
                    bot_id=r.bot_id,
                    message=r.message[:_MESSAGE_MAX_LENGTH] if r.message else None,
                    create_time=r.create_time,
                )
                for r in records
            ]
            await ChatHistory.bulk_add(history_list)
            logger.debug(f"批量写入聊天记录 {len(records)} 条", LOG_COMMAND)
        except Exception as e:
            logger.error("批量写入聊天记录失败", LOG_COMMAND, e=e)


@PriorityLifecycle.on_startup(priority=10)
async def _start_chat_history_queue():
    """启动聊天记录队列处理。"""
    await ChatHistoryQueue.start()
    logger.info("聊天记录队列已启动", LOG_COMMAND)


@PriorityLifecycle.on_shutdown(priority=10)
async def _stop_chat_history_queue():
    """停止聊天记录队列并刷写剩余记录。"""
    await ChatHistoryQueue.stop()
    logger.info("聊天记录队列已停止", LOG_COMMAND)


_matcher = on_message(priority=10, block=False)


@_matcher.handle()
async def _(session: Uninfo, event: Event, message: UniMsg):
    """记录聊天消息"""
    if not Config.get_config("hook", "CHAT_HISTORY_ENABLE"):
        return

    user_id = session.user.id
    if not user_id or user_id == session.self_id:
        return

    group_id = None
    if session.group:
        group_id = (
            session.group.parent.id if session.group.parent else session.group.id
        )

    text = message.extract_plain_text() if message else event.get_plaintext()
    ChatHistoryQueue.add(
        ChatHistoryRecord(
            user_id=user_id,
            group_id=group_id,
            bot_id=session.self_id,
            message=text or None,
            create_time=datetime.now(),
        )
    )
