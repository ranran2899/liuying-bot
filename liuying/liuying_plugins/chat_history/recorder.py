"""聊天记录核心处理"""

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from nonebot.adapters import Event
from nonebot_plugin_alconna import UniMsg
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.config import Config
from liuying.models.chat_history import ChatHistory
from liuying.utils.batch_queue import BatchQueue
from liuying.utils.log import logger

_MESSAGE_MAX_LENGTH = 5000

LOG_COMMAND = "ChatHistoryHook"


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


class ChatHistoryHook:
    """聊天记录钩子，解析会话并批量入库"""

    _batch_queue: ClassVar[BatchQueue[ChatHistoryRecord]] = BatchQueue[
        ChatHistoryRecord
    ]("聊天记录", _write_records)

    @classmethod
    def record(cls, session: Uninfo, event: Event, message: UniMsg) -> None:
        """解析会话信息并加入写入队列

        参数:
            session: 会话信息
            event: 事件对象
            message: 消息内容
        """
        if not Config.get_config("chat_history", "CHAT_HISTORY_ENABLE"):
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
        cls._batch_queue.add(
            ChatHistoryRecord(
                user_id=user_id,
                group_id=group_id,
                bot_id=session.self_id,
                message=text or None,
                create_time=datetime.now(),
            )
        )

    @classmethod
    async def start(cls, interval: int, size: int) -> None:
        """启动批量写入队列

        参数:
            interval: 批量写入间隔（秒）
            size: 批量写入最大数量
        """
        await cls._batch_queue.start(interval, size)

    @classmethod
    async def stop(cls) -> None:
        """停止批量写入队列"""
        await cls._batch_queue.stop()
