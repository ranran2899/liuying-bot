"""消息批量缓冲器

按会话缓存短时间内的多条消息，合并为一条后统一处理，
减少高频对话场景下的重复回复，提升对话节奏感。

缓冲窗口：
- 群聊：1.2秒（用户可能在短时间内连续发言）
- 私聊：0.8秒（私聊节奏更快）

工作流程：
1. 第一条消息进入缓冲区，触发窗口期等待
2. 窗口期内的后续消息追加到缓冲区，立即返回None
3. 窗口期结束后，第一条消息的协程拿到合并文本继续处理

并发安全：利用 asyncio 单线程特性，从检查缓冲区到创建缓冲区
之间无 await 点，保证原子性，无需显式锁。
"""

import asyncio
from dataclasses import dataclass, field

from liuying.utils.log import logger

from ..config import get_config

__all__ = ["ReplyBuffer", "reply_buffer"]

_DEFAULT_GROUP_DELAY = 1.2
"""默认群聊缓冲窗口（秒）"""

_DEFAULT_PRIVATE_DELAY = 0.8
"""默认私聊缓冲窗口（秒）"""

_MAX_BUFFER_ITEMS = 10
"""单次合并最大消息数，防止恶意刷屏"""


@dataclass(slots=True)
class _BufferEntry:
    """缓冲区条目

    Attributes:
        texts: 已缓冲的文本列表
        flushed: 是否已flush（窗口期已结束）
        first_message_id: 第一条消息的ID（用于引用回复等）
    """

    texts: list[str] = field(default_factory=list)
    flushed: bool = False
    first_message_id: int | None = None


class ReplyBuffer:
    """消息批量缓冲器

    按会话隔离缓冲区，窗口期内合并多条消息。
    第一条消息的协程等待窗口期后返回合并文本，
    后续消息立即返回None表示已被合并。
    """

    def __init__(self) -> None:
        """初始化消息批量缓冲器"""
        self._buffers: dict[str, _BufferEntry] = {}

    def _get_window(self, is_private: bool) -> float:
        """获取缓冲窗口时长

        参数:
            is_private: 是否私聊

        返回:
            float: 窗口时长（秒）
        """
        buffer_cfg = get_config("REPLY_BUFFER", {})
        key = "private_delay" if is_private else "group_delay"
        default = (
            _DEFAULT_PRIVATE_DELAY if is_private else _DEFAULT_GROUP_DELAY
        )
        try:
            return float(buffer_cfg.get(key, default))
        except (TypeError, ValueError):
            return float(default)

    async def submit(
        self,
        session_key: str,
        text: str,
        is_private: bool,
        message_id: int | None = None,
    ) -> str | None:
        """提交消息到缓冲区

        第一条消息触发窗口期等待，收集窗口期内的所有消息，
        返回合并后的文本。后续消息返回None（已被合并）。

        并发安全：从检查缓冲区到创建缓冲区之间无await点，
        利用asyncio单线程特性保证原子性。

        参数:
            session_key: 会话标识（如 user_id 或 group_id:user_id）
            text: 消息文本
            is_private: 是否私聊
            message_id: 消息ID（用于记录首条消息）

        返回:
            str | None: 合并后的文本（仅首条消息返回），
                None表示已被合并到前一条消息
        """
        entry = self._buffers.get(session_key)
        if entry is not None and not entry.flushed:
            # 后续消息：追加到缓冲区（list.append是原子操作）
            if len(entry.texts) < _MAX_BUFFER_ITEMS:
                entry.texts.append(text)
            return None

        # 第一条消息：创建缓冲区并等待窗口期
        # 此时无await点，后续协程不会在此插入
        return await self._create_and_wait(
            session_key, text, is_private, message_id
        )

    async def _create_and_wait(
        self,
        session_key: str,
        text: str,
        is_private: bool,
        message_id: int | None,
    ) -> str:
        """创建缓冲区条目并等待窗口期

        参数:
            session_key: 会话标识
            text: 首条消息文本
            is_private: 是否私聊
            message_id: 首条消息ID

        返回:
            str: 窗口期结束后合并的文本
        """
        entry = _BufferEntry(
            texts=[text],
            first_message_id=message_id,
        )
        self._buffers[session_key] = entry

        window = self._get_window(is_private)
        try:
            await asyncio.sleep(window)
        except asyncio.CancelledError:
            # 首条协程被取消（如 matcher 超时）：标记已flush，
            # 避免后续消息被永久合并吞没
            entry.flushed = True
            raise
        finally:
            # 无论正常/异常，确保清理缓冲区，杜绝僵尸 entry
            self._buffers.pop(session_key, None)

        # 窗口期结束，收集合并文本
        entry.flushed = True
        combined_texts = list(entry.texts)
        first_message_id = entry.first_message_id

        combined = "\n".join(t for t in combined_texts if t)
        if len(combined_texts) > 1:
            logger.debug(
                f"消息批量缓冲合并: session={session_key} "
                f"count={len(combined_texts)} "
                f"first_msg_id={first_message_id}",
                command="AI",
            )
        return combined

    def clear(self, session_key: str | None = None) -> None:
        """清理缓冲区

        参数:
            session_key: 指定会话标识，None时清理全部
        """
        if session_key is None:
            self._buffers.clear()
        else:
            self._buffers.pop(session_key, None)


reply_buffer = ReplyBuffer()
"""消息批量缓冲器单例"""
