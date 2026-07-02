"""回复缓冲与抢占

session 维度的批次缓冲：新消息进入后启动 delay 计时器，
delay 内累积的同类消息合并成一批处理。
当批次处理中又收到 immediate_flush（直@、引用bot、私聊）时，
通过 generation 代次机制抢占旧批次，旧回复会被丢弃。
"""

import asyncio
from dataclasses import dataclass, field
import time
from typing import Any

from liuying.utils.log import logger

__all__ = [
    "BufferItem",
    "ReplyBuffer",
    "reply_buffer",
]


_GROUP_BATCH_DELAY_SECONDS = 1.2
"""群聊批次缓冲延迟（秒）"""


_PRIVATE_BATCH_DELAY_SECONDS = 0.8
"""私聊批次缓冲延迟（秒）"""


_MAX_BATCH_EVENTS = 8
"""单个批次最大消息数"""


_PROCESS_RESPONSE_TIMEOUT_SECONDS = 180.0
"""单轮回复处理超时（秒）"""


_DIRECT_REPLY_PREEMPT_SECONDS = 8.0
"""直呼消息抢占阈值（处理超过此秒数才抢占）"""


@dataclass(slots=True)
class BufferItem:
    """缓冲消息项

    Attributes:
        user_id: 用户ID
        text: 消息文本
        group_id: 群组ID
        is_private: 是否私聊
        is_direct_mention: 是否直接@机器人
        timestamp: 进入缓冲时间戳
    """

    user_id: str
    text: str
    group_id: str | None
    is_private: bool
    is_direct_mention: bool
    timestamp: float = field(default_factory=time.time)


@dataclass(slots=True)
class BufferEntry:
    """缓冲条目

    Attributes:
        items: 已缓冲的消息列表
        pending_items: 待处理的消息列表
        processing: 是否正在处理
        active_task: 活跃任务
        processing_started_at: 处理开始时间
        current_is_direct: 当前是否为直接@
        timer_task: 定时器任务
        delay: 批次延迟秒数
        current_generation: 当前代数
        superseded_generation: 被取代的代数
        newer_batch_for_current: 是否有更新的批次
    """

    items: list = field(default_factory=list)
    pending_items: list = field(default_factory=list)
    processing: bool = False
    active_task: Any = None
    processing_started_at: float = 0.0
    current_is_direct: bool = False
    timer_task: Any = None
    delay: float = 0.0
    current_generation: int = 0
    superseded_generation: int = 0
    newer_batch_for_current: bool = False


def _session_key(
    user_id: str,
    group_id: str | None,
    is_private: bool,
) -> str:
    """生成会话键

    参数:
        user_id: 用户ID
        group_id: 群组ID
        is_private: 是否私聊

    返回:
        str: 会话键
    """
    if is_private:
        return f"private:{user_id}"
    return f"group:{group_id}"


def _should_preempt_current_batch(
    entry: dict[str, Any],
    *,
    immediate_flush: bool,
) -> bool:
    """判断是否应该抢占当前处理中的批次

    参数:
        entry: 缓冲条目
        immediate_flush: 是否立即刷新（直@、引用、私聊）

    返回:
        bool: 是否应该抢占
    """
    if not immediate_flush or not bool(entry.get("processing")):
        return False

    if bool(entry.get("newer_batch_for_current")):
        return True

    started_at = float(entry.get("processing_started_at", 0.0) or 0.0)
    if started_at <= 0:
        return False
    return (time.time() - started_at) >= _DIRECT_REPLY_PREEMPT_SECONDS


def _trim_items(items: list[BufferItem]) -> list[BufferItem]:
    """截断批次消息数

    参数:
        items: 消息列表

    返回:
        list[BufferItem]: 截断后的列表
    """
    if len(items) <= _MAX_BATCH_EVENTS:
        return items
    return items[-_MAX_BATCH_EVENTS:]


class ReplyBuffer:
    """回复缓冲管理器

    按 session 维度缓冲消息，支持批次合并与抢占。
    """

    def __init__(self) -> None:
        """初始化回复缓冲管理器"""
        self._entries: dict[str, dict[str, Any]] = {}
        self._handlers: dict[
            str,
            Any,
        ] = {}

    def register_handler(
        self,
        handler_type: str,
        handler: Any,
    ) -> None:
        """注册批处理回调

        参数:
            handler_type: 处理器类型
            handler: 处理器对象
        """
        self._handlers[handler_type] = handler

    def _batch_delay(self, is_private: bool) -> float:
        """获取批次延迟

        参数:
            is_private: 是否私聊

        返回:
            float: 延迟秒数
        """
        return (
            _PRIVATE_BATCH_DELAY_SECONDS
            if is_private
            else _GROUP_BATCH_DELAY_SECONDS
        )

    def get_entry(
        self,
        session_key: str,
        is_private: bool,
    ) -> BufferEntry:
        """获取或创建缓冲条目

        参数:
            session_key: 会话键
            is_private: 是否私聊

        返回:
            BufferEntry: 缓冲条目
        """
        entry = self._entries.get(session_key)
        if entry is None:
            entry = BufferEntry(delay=self._batch_delay(is_private))
            self._entries[session_key] = entry
        return entry

    def is_stale_generation(
        self,
        session_key: str,
        generation: int,
    ) -> bool:
        """检测批次是否已过时（应被丢弃）

        参数:
            session_key: 会话键
            generation: 待检测的代次

        返回:
            bool: True表示已过时应丢弃
        """
        entry = self._entries.get(session_key)
        if not isinstance(entry, dict):
            return False

        if int(entry.get("superseded_generation", 0) or 0) >= generation:
            return True
        if int(entry.get("current_generation", 0) or 0) != generation:
            return True
        return False

    def abort_if_stale(
        self,
        session_key: str,
        generation: int,
    ) -> bool:
        """过时则记录日志并返回True

        参数:
            session_key: 会话键
            generation: 代次

        返回:
            bool: 是否过时
        """
        if self.is_stale_generation(session_key, generation):
            logger.info(
                f"会话 {session_key} 代次 {generation} 已被抢占，丢弃旧回复",
                command="AI",
            )
            return True
        return False

    async def submit(
        self,
        item: BufferItem,
        process_callback: Any,
    ) -> None:
        """提交消息到缓冲并启动/抢占处理

        参数:
            item: 消息项
            process_callback: 处理回调（接受 items 列表与 generation）
        """
        session_key = _session_key(
            item.user_id, item.group_id, item.is_private
        )
        entry = self.get_entry(session_key, item.is_private)
        immediate_flush = (
            item.is_private or item.is_direct_mention
        )

        if entry.processing:
            pending = list(entry.pending_items)
            pending.append(item)
            entry.pending_items = _trim_items(pending)
            entry.newer_batch_for_current = True

            if immediate_flush and _should_preempt_current_batch(
                entry, immediate_flush=True
            ):
                entry.superseded_generation = max(
                    entry.superseded_generation,
                    entry.current_generation,
                )
                active_task = entry.active_task
                if active_task and not active_task.done():
                    active_task.cancel()
                    logger.info(
                        f"会话 {session_key} 收到新的直呼消息，"
                        f"抢占当前旧批次",
                        command="AI",
                    )
            return

        items = list(entry.items)
        items.append(item)
        entry.items = _trim_items(items)
        entry.current_is_direct = immediate_flush

        timer_task = entry.timer_task
        if timer_task and not timer_task.done():
            return

        async def _timer_fire() -> None:
            """定时器到期触发批次处理"""
            try:
                await asyncio.sleep(entry.delay)
            except asyncio.CancelledError:
                return

            await self._dispatch_batch(
                session_key, entry, process_callback
            )

        entry.timer_task = asyncio.create_task(_timer_fire())

    async def _dispatch_batch(
        self,
        session_key: str,
        entry: BufferEntry,
        process_callback: Any,
    ) -> None:
        """派发批次到处理回调

        参数:
            session_key: 会话键
            entry: 缓冲条目
            process_callback: 处理回调
        """
        items = list(entry.items)
        if not items:
            return

        entry.items = []
        entry.processing = True
        entry.processing_started_at = time.time()
        entry.current_generation += 1
        entry.newer_batch_for_current = False
        generation = entry.current_generation

        async def _run() -> None:
            """运行批次处理"""
            try:
                await asyncio.wait_for(
                    process_callback(items, generation),
                    timeout=_PROCESS_RESPONSE_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                logger.warning(
                    f"会话 {session_key} 批次处理超时"
                    f"（>{_PROCESS_RESPONSE_TIMEOUT_SECONDS:.0f}s），"
                    f"已放弃旧批次",
                    command="AI",
                )
            except asyncio.CancelledError:
                if entry.superseded_generation >= generation:
                    logger.info(
                        f"会话 {session_key} 当前批次已被新的直呼"
                        f"消息抢占",
                        command="AI",
                    )
                raise
            except Exception as exc:
                logger.warning(
                    f"会话 {session_key} 批次处理失败: {exc}",
                    command="AI",
                    e=exc,
                )
            finally:
                entry.processing = False
                entry.processing_started_at = 0.0
                entry.active_task = None

                pending = list(entry.pending_items)
                if pending:
                    entry.items = pending
                    entry.pending_items = []
                    entry.newer_batch_for_current = False

                    async def _next_fire() -> None:
                        """下一轮定时器"""
                        try:
                            await asyncio.sleep(entry.delay)
                        except asyncio.CancelledError:
                            return
                        await self._dispatch_batch(
                            session_key, entry, process_callback
                        )

                    entry.timer_task = asyncio.create_task(
                        _next_fire()
                    )
                else:
                    entry.timer_task = None

        entry.active_task = asyncio.create_task(_run())


reply_buffer = ReplyBuffer()
"""回复缓冲单例"""
