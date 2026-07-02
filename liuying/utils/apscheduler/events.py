"""
定时任务事件系统
提供任务生命周期的事件回调机制
"""

import asyncio
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
import uuid

from liuying.utils.log import logger


class TaskEventType(StrEnum):
    """任务事件类型"""

    TASK_ADDED = "task_added"
    """任务已添加"""
    TASK_REMOVED = "task_removed"
    """任务已移除"""
    TASK_MODIFIED = "task_modified"
    """任务已修改"""
    TASK_STARTED = "task_started"
    """任务开始执行"""
    TASK_FINISHED = "task_finished"
    """任务执行完成"""
    TASK_FAILED = "task_failed"
    """任务执行失败"""
    TASK_MISSED = "task_missed"
    """任务错过执行"""
    TASK_PAUSED = "task_paused"
    """任务已暂停"""
    TASK_RESUMED = "task_resumed"
    """任务已恢复"""
    TASK_TIMEOUT = "task_timeout"
    """任务执行超时"""
    TASK_RETRY = "task_retry"
    """任务重试"""
    GROUP_PAUSED = "group_paused"
    """分组已暂停"""
    GROUP_RESUMED = "group_resumed"
    """分组已恢复"""
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
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    """事件唯一标识"""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.name,
            "task_id": self.task_id,
            "task_name": self.task_name,
            "group": self.group,
            "trigger_type": self.trigger_type,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
        }


class TaskEventBus:
    """任务事件总线"""

    def __init__(self, max_history: int = 1000) -> None:
        self._subscribers: dict[TaskEventType, list[Callable[[TaskEvent], Any]]] = {}
        self._all_subscribers: list[Callable[[TaskEvent], Any]] = []
        self._event_history: deque[TaskEvent] = deque(maxlen=max_history)
        self._max_history = max_history

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
        if event_type is None:
            self._all_subscribers.append(callback)
        elif isinstance(event_type, list):
            for et in event_type:
                if et not in self._subscribers:
                    self._subscribers[et] = []
                self._subscribers[et].append(callback)
        else:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(callback)

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
        if event_type is None:
            if callback in self._all_subscribers:
                self._all_subscribers.remove(callback)
        elif isinstance(event_type, list):
            for et in event_type:
                if et in self._subscribers and callback in self._subscribers[et]:
                    self._subscribers[et].remove(callback)
        else:
            if event_type in self._subscribers:
                if callback in self._subscribers[event_type]:
                    self._subscribers[event_type].remove(callback)

    async def emit(self, event: TaskEvent) -> None:
        """
        发布事件

        参数:
            event: 任务事件
        """
        # 保存到历史记录（deque 自动淘汰旧记录，append 原子无需加锁）
        self._event_history.append(event)

        # 收集所有需要通知的回调
        callbacks = list(self._all_subscribers)
        if event.event_type in self._subscribers:
            callbacks.extend(self._subscribers[event.event_type])

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
                    f"事件回调执行失败: {callback.__name__}", e=e
                )

        # 等待所有异步任务完成
        if async_tasks:
            await asyncio.gather(*async_tasks, return_exceptions=True)

    def get_history(
        self,
        event_type: TaskEventType | None = None,
        limit: int = 100,
    ) -> list[TaskEvent]:
        """
        获取事件历史

        参数:
            event_type: 事件类型过滤
            limit: 返回数量限制

        返回:
            事件列表
        """
        events = list(self._event_history)
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return events[-limit:]

    def clear_history(self) -> None:
        """清空事件历史"""
        self._event_history.clear()


# 全局事件总线实例
event_bus = TaskEventBus()


def on_event(
    event_type: TaskEventType | list[TaskEventType] | None,
) -> Callable[[Callable[[TaskEvent], Any]], Callable[[TaskEvent], Any]]:
    """
    事件订阅装饰器

    使用示例:
        @on_event(TaskEventType.TASK_FAILED)
        async def handle_task_failed(event: TaskEvent):
            print(f"任务失败: {event.task_name}")

    参数:
        event_type: 事件类型

    返回:
        装饰器
    """

    def decorator(func: Callable[[TaskEvent], Any]) -> Callable[[TaskEvent], Any]:
        event_bus.subscribe(event_type, func)
        return func

    return decorator
