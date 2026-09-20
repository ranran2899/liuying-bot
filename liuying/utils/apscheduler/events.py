"""
定时任务事件系统

提供任务生命周期的事件回调机制，采用发布订阅模式解耦调度器与监听器。
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from liuying.utils.log import logger

_LOG_COMMAND = "SchedulerEvents"


class TaskEventType(StrEnum):
    """任务事件类型（仅包含实际会发布的事件）"""

    TASK_STARTED = "task_started"
    """任务开始执行"""
    TASK_FINISHED = "task_finished"
    """任务执行完成"""
    TASK_FAILED = "task_failed"
    """任务执行失败"""
    TASK_MISSED = "task_missed"
    """任务错过执行"""
    ALERT_TRIGGERED = "alert_triggered"
    """告警已触发"""


@dataclass(slots=True)
class TaskEvent:
    """任务事件"""

    event_type: TaskEventType
    """事件类型"""
    task_id: str | None = None
    """任务ID"""
    task_name: str | None = None
    """任务名称"""
    group: str | None = None
    """分组名称"""
    trigger_type: str | None = None
    """触发器类型"""
    timestamp: datetime = field(default_factory=datetime.now)
    """事件时间戳"""
    data: dict[str, Any] = field(default_factory=dict)
    """事件附加数据"""


class TaskEventBus:
    """任务事件总线（单线程 asyncio 模型，无需加锁）"""

    def __init__(self) -> None:
        self._subscribers: dict[
            TaskEventType, list[Callable[[TaskEvent], Any]]
        ] = {}
        self._all_subscribers: list[Callable[[TaskEvent], Any]] = []

    def subscribe(
        self,
        event_type: TaskEventType | list[TaskEventType] | None,
        callback: Callable[[TaskEvent], Any],
    ) -> None:
        """
        订阅事件

        参数:
            event_type: 事件类型，None表示订阅所有事件
            callback: 事件回调函数
        """
        match event_type:
            case None:
                self._all_subscribers.append(callback)
            case list() as types:
                for et in types:
                    self._subscribers.setdefault(et, []).append(callback)
            case TaskEventType() as et:
                self._subscribers.setdefault(et, []).append(callback)

    def _remove_subscriber(
        self,
        event_type: TaskEventType,
        callback: Callable[[TaskEvent], Any],
    ) -> None:
        """从指定类型的订阅列表移除回调"""
        subs = self._subscribers.get(event_type)
        if subs and callback in subs:
            subs.remove(callback)

    def unsubscribe(
        self,
        event_type: TaskEventType | list[TaskEventType] | None,
        callback: Callable[[TaskEvent], Any],
    ) -> None:
        """
        取消订阅事件

        参数:
            event_type: 事件类型，None表示取消所有事件的订阅
            callback: 事件回调函数
        """
        match event_type:
            case None:
                if callback in self._all_subscribers:
                    self._all_subscribers.remove(callback)
            case list() as types:
                for et in types:
                    self._remove_subscriber(et, callback)
            case TaskEventType() as et:
                self._remove_subscriber(et, callback)

    async def emit(self, event: TaskEvent) -> None:
        """
        发布事件

        参数:
            event: 任务事件
        """
        # 收集所有需要通知的回调
        callbacks = list(self._all_subscribers)
        callbacks.extend(self._subscribers.get(event.event_type, ()))

        if not callbacks:
            return

        # 分别处理同步和异步回调
        async_tasks: list[asyncio.Task] = []
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    async_tasks.append(asyncio.create_task(callback(event)))
                else:
                    callback(event)
            except Exception as e:
                logger.error(
                    f"事件回调执行失败: {callback.__name__}",
                    _LOG_COMMAND,
                    e=e,
                )

        # 等待所有异步任务完成
        if async_tasks:
            await asyncio.gather(*async_tasks, return_exceptions=True)


# 全局事件总线实例
event_bus = TaskEventBus()
