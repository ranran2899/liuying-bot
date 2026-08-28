"""聊天记录钩子"""

from dataclasses import dataclass
from datetime import datetime

from nonebot import on_message
from nonebot.adapters import Event
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import UniMsg
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.config import Config
from liuying.configs.utils import PluginExtraData
from liuying.models.chat_history import ChatHistory
from liuying.utils.batch_queue import BatchQueue
from liuying.utils.enum import PluginType
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

__plugin_meta__ = PluginMetadata(
    name="chat_history_hook",
    description="记录聊天消息到数据库",
    usage="被动记录，无需命令触发",
    extra=PluginExtraData(
        plugin_type=PluginType.HIDDEN,
        is_show=False,
    ).to_dict(),
)


@dataclass(slots=True)
class ChatHistoryRecord:
    """聊天记录数据"""

    user_id: str | None
    group_id: str | None
    bot_id: str
    message: str | None
    create_time: datetime


async def _write_records(records: list[ChatHistoryRecord]) -> None:
    """批量写入聊天记录

    参数:
        records: 聊天记录列表
    """
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


_batch_queue = BatchQueue[ChatHistoryRecord]("聊天记录", _write_records)


@PriorityLifecycle.on_startup(priority=10)
async def _start_chat_history_queue():
    """启动聊天记录队列处理"""
    await _batch_queue.start(
        Config.get_config("hook", "CHAT_HISTORY_BATCH_INTERVAL") or 60,
        Config.get_config("hook", "CHAT_HISTORY_BATCH_SIZE") or 100,
    )


@PriorityLifecycle.on_shutdown(priority=10)
async def _stop_chat_history_queue():
    """停止聊天记录队列处理"""
    await _batch_queue.stop()


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
    _batch_queue.add(
        ChatHistoryRecord(
            user_id=user_id,
            group_id=group_id,
            bot_id=session.self_id,
            message=text or None,
            create_time=datetime.now(),
        )
    )
