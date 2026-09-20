"""
核心调度器

负责任务调度、优先级管理、依赖关系处理，采用懒删除的优先级队列优化性能。
调度器持有的 TaskEntry 是任务运行时状态的唯一数据源，
管理器层直接共享同一实例，无需双向同步。
"""

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import heapq
import time
from typing import Any
from uuid import uuid4

from liuying.models.scheduler_job import SchedulerJob
from liuying.utils.enum import TaskStatus, TriggerType
from liuying.utils.log import logger

from .alert import alert_manager
from .constants import (
    COMPLETED_TASK_TTL,
    SCHEDULER_DEPENDENCY_RETRY_DELAY,
    SCHEDULER_RUN_NOW_PRIORITY,
    SCHEDULER_SHUTDOWN_WAIT,
)
from .events import TaskEvent, TaskEventType, event_bus
from .executor import ExecutionResult, TaskExecutor
from .metrics import metrics_collector
from .models import TaskConfig, TaskInfo
from .triggers import BaseTrigger, DateTrigger

_LOG_COMMAND = "Scheduler"


@dataclass(order=True, slots=True)
class ScheduledTask:
    """调度队列条目（time-first，同刻按 priority 排序）"""

    next_run_time: datetime
    """下次运行时间"""
    task_id: str = field(compare=False)
    """任务ID"""
    priority: int = field(default=0, compare=True)
    """优先级，数值越小优先级越高"""
    version: int = field(default=0, compare=False)
    """版本号，用于懒删除校验"""


@dataclass(slots=True)
class TaskEntry(TaskInfo):
    """
    调度器任务条目（继承自统一任务模型）

    在 TaskInfo 基础上添加调度器所需的触发器实例和运行时属性。
    管理器与调度器共享同一实例，状态变更天然一致。
    """

    trigger: BaseTrigger | None = field(default=None, repr=False)
    """触发器实例"""
    _version: int = field(default=0, repr=False)
    """版本计数器，用于懒删除"""
    _cached_next_run_time: datetime | None = field(default=None, repr=False)
    """缓存的下次运行时间，避免重复计算 CronTrigger"""

    @property
    def version(self) -> int:
        """当前版本号"""
        return self._version

    def bump_version(self) -> int:
        """递增版本号并返回新值"""
        self._version += 1
        return self._version

    @property
    def next_run_time(self) -> datetime | None:
        """下次运行时间（返回缓存值，由 refresh_next_run_time 刷新）"""
        return self._cached_next_run_time

    def refresh_next_run_time(self) -> None:
        """刷新下次运行时间缓存"""
        match self.trigger:
            case DateTrigger() as date_trigger:
                self._cached_next_run_time = date_trigger.run_date
            case BaseTrigger() as trigger:
                self._cached_next_run_time = trigger.get_next_run_time(
                    self.last_run_time
                )
            case _:
                self._cached_next_run_time = None


class Scheduler:
    """
    核心调度器

    负责：
    - 任务调度循环
    - 优先级队列管理（懒删除优化）
    - 任务依赖关系处理
    - 错过执行处理
    """

    def __init__(self) -> None:
        self._tasks: dict[str, TaskEntry] = {}
        self._priority_queue: list[ScheduledTask] = []
        self._executor = TaskExecutor()
        self._running = False
        self._scheduler_task: asyncio.Task | None = None
        self._wakeup_event = asyncio.Event()
        self._completed_tasks: dict[str, float] = {}
        """已完成一次性任务记录（task_id -> 完成时间戳，带 TTL）"""

        # 初始化辅助系统
        self._event_bus = event_bus
        self._metrics = metrics_collector
        self._alert_manager = alert_manager

    async def start(self) -> None:
        """启动调度器"""
        if self._running:
            return

        self._running = True
        self._scheduler_task = asyncio.create_task(self._run_loop())
        logger.info("定时任务调度器已启动", _LOG_COMMAND)

    async def stop(self, wait: bool = True) -> None:
        """停止调度器"""
        self._running = False
        self._wakeup_event.set()

        scheduler_task = self._scheduler_task
        self._scheduler_task = None
        if scheduler_task:
            if wait:
                try:
                    async with asyncio.timeout(SCHEDULER_SHUTDOWN_WAIT):
                        await scheduler_task
                except TimeoutError:
                    scheduler_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await scheduler_task
            else:
                scheduler_task.cancel()

        await self._executor.shutdown()
        logger.info("定时任务调度器已停止", _LOG_COMMAND)

    @staticmethod
    def _generate_task_id(config: TaskConfig) -> str:
        """为未指定 task_id 的任务生成唯一标识

        参数:
            config: 任务配置

        返回:
            形如 "{函数名}_{短uuid}" 的任务ID
        """
        base = getattr(config.func, "__name__", "") or config.trigger_type.value
        return f"{base}_{uuid4().hex[:8]}"

    def add_task(self, config: TaskConfig, trigger: BaseTrigger) -> TaskEntry:
        """添加任务（TaskEntry 作为运行时状态的单一数据源）

        参数:
            config: 任务配置（task_id/name 为空时自动补全）
            trigger: 触发器实例

        返回:
            创建的任务条目

        异常:
            ValueError: 任务已存在且不允许替换，或存在循环依赖
        """
        # 未指定任务ID时自动生成，并确保与现有任务不冲突
        if not config.task_id:
            config.task_id = self._generate_task_id(config)
            while config.task_id in self._tasks:
                config.task_id = self._generate_task_id(config)
        if not config.name:
            config.name = config.task_id

        task_id = config.task_id
        if task_id in self._tasks and not config.replace_existing:
            raise ValueError(
                f"任务 '{task_id}' 已存在,请使用 replace_existing=True 来替换"
            )

        if config.dependencies and (
            cycle := self._detect_cycle(task_id, config.dependencies)
        ):
            raise ValueError(f"检测到循环依赖: {' -> '.join(cycle)}")

        entry = TaskEntry(
            id=task_id, name=config.name, trigger=trigger, func=config.func,
            args=config.args, kwargs=config.kwargs, group=config.group,
            priority=config.priority, max_instances=config.max_instances,
            misfire_grace_time=config.misfire_grace_time,
            dependencies=config.dependencies, description=config.description,
            trigger_type=config.trigger_type,
            trigger_config=config.trigger_config,
            status=TaskStatus.RUNNING, save_to_db=config.save_to_db,
        )

        self._tasks[task_id] = entry
        self._schedule_task(entry)
        self._update_metrics()
        return entry

    def _detect_cycle(
        self,
        task_id: str,
        dependencies: list[str],
    ) -> list[str] | None:
        """
        检测循环依赖（三色 DFS 算法）

        参数:
            task_id: 当前任务ID
            dependencies: 依赖列表

        返回:
            如果存在循环依赖，返回循环路径；否则返回 None
        """
        # 三色标记: 0=WHITE 未访问, 1=GRAY 路径栈中, 2=BLACK 已完成
        color: dict[str, int] = {}
        path: list[str] = []

        def dfs(current_id: str, deps: list[str]) -> list[str] | None:
            """深度优先搜索"""
            color[current_id] = 1
            path.append(current_id)

            for dep_id in deps:
                dep_color = color.get(dep_id, 0)
                if dep_color == 1:
                    # 遇到 GRAY 节点，找到环
                    cycle_start = path.index(dep_id)
                    return [*path[cycle_start:], dep_id]
                if dep_color == 0:
                    dep_entry = self._tasks.get(dep_id)
                    dep_deps = dep_entry.dependencies if dep_entry else []
                    result = dfs(dep_id, dep_deps)
                    if result:
                        return result

            path.pop()
            color[current_id] = 2
            return None

        return dfs(task_id, dependencies)

    def _schedule_task(self, entry: TaskEntry) -> None:
        """将任务加入调度队列（带版本号，支持懒删除）"""
        entry.refresh_next_run_time()
        next_time = entry.next_run_time

        if next_time is None:
            return

        if next_time.tzinfo is not None:
            next_time = next_time.replace(tzinfo=None)

        heapq.heappush(
            self._priority_queue,
            ScheduledTask(
                next_run_time=next_time,
                task_id=entry.id,
                priority=entry.priority,
                version=entry.version,
            ),
        )
        self._wakeup_event.set()

    def _reschedule_after_delay(
        self,
        entry: TaskEntry,
        seconds: float = SCHEDULER_DEPENDENCY_RETRY_DELAY,
    ) -> None:
        """延迟指定秒数后重新调度任务（依赖未满足/并发已满等场景，避免忙等）"""
        heapq.heappush(
            self._priority_queue,
            ScheduledTask(
                next_run_time=datetime.now() + timedelta(seconds=seconds),
                task_id=entry.id,
                priority=entry.priority,
                version=entry.version,
            ),
        )
        self._wakeup_event.set()

    def remove_task(self, task_id: str) -> bool:
        """移除任务（懒删除：递增版本号使旧条目自动失效）"""
        if task_id not in self._tasks:
            return False

        self._tasks[task_id].bump_version()
        del self._tasks[task_id]

        self._update_metrics()
        return True

    def pause_task(self, task_id: str) -> bool:
        """暂停任务（懒删除：递增版本号使旧条目失效）"""
        if task_id not in self._tasks:
            return False

        entry = self._tasks[task_id]
        entry.status = TaskStatus.PAUSED
        entry.bump_version()

        self._update_metrics()
        return True

    def resume_task(self, task_id: str) -> bool:
        """恢复任务"""
        if task_id not in self._tasks:
            return False

        entry = self._tasks[task_id]
        entry.status = TaskStatus.RUNNING
        self._schedule_task(entry)

        self._update_metrics()
        return True

    def modify_task(
        self,
        task_id: str,
        trigger: BaseTrigger | None = None,
        trigger_type: TriggerType | None = None,
        trigger_config: dict[str, Any] | None = None,
        *,
        name: str | None = None,
        group: str | None = None,
        priority: int | None = None,
        max_instances: int | None = None,
        description: str | None = None,
        misfire_grace_time: int | None = None,
    ) -> bool:
        """修改任务（仅允许显式字段，直接变更共享的 TaskEntry）"""
        if task_id not in self._tasks:
            return False

        entry = self._tasks[task_id]

        if trigger is not None:
            entry.trigger = trigger
        if trigger_type is not None:
            entry.trigger_type = trigger_type
        if trigger_config:
            entry.trigger_config.update(trigger_config)
        if name is not None:
            entry.name = name
        if group is not None:
            entry.group = group
        if priority is not None:
            entry.priority = priority
        if max_instances is not None:
            entry.max_instances = max_instances
        if description is not None:
            entry.description = description
        if misfire_grace_time is not None:
            entry.misfire_grace_time = misfire_grace_time

        entry.bump_version()

        if entry.status == TaskStatus.RUNNING:
            self._schedule_task(entry)

        return True

    def run_task_now(self, task_id: str) -> bool:
        """立即执行任务"""
        if task_id not in self._tasks:
            return False

        entry = self._tasks[task_id]
        heapq.heappush(
            self._priority_queue,
            ScheduledTask(
                next_run_time=datetime.now(),
                task_id=entry.id,
                priority=SCHEDULER_RUN_NOW_PRIORITY,
                version=entry.version,
            ),
        )
        self._wakeup_event.set()
        return True

    async def _run_loop(self) -> None:
        """调度循环"""
        while self._running:
            try:
                self._process_tasks()

                wait_time = self._get_next_wait_time()
                if wait_time is None:
                    await self._wakeup_event.wait()
                    self._wakeup_event.clear()
                elif wait_time > 0:
                    try:
                        await asyncio.wait_for(
                            self._wakeup_event.wait(), timeout=wait_time
                        )
                        self._wakeup_event.clear()
                    except TimeoutError:
                        pass

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("调度循环异常", _LOG_COMMAND, e=e)
                await asyncio.sleep(1)

    def _process_tasks(self) -> None:
        """处理到期任务（批量弹出同一时刻内的多个任务）"""
        while self._priority_queue:
            scheduled = self._priority_queue[0]

            if scheduled.next_run_time > datetime.now():
                break

            heapq.heappop(self._priority_queue)

            entry = self._tasks.get(scheduled.task_id)

            # 懒删除校验：条目被删除或版本不匹配则跳过
            if entry is None or entry.version != scheduled.version:
                continue

            if entry.status != TaskStatus.RUNNING:
                continue

            if self._check_misfire(entry, scheduled):
                self._handle_misfire(entry)
                continue

            if not self._check_dependencies(entry):
                self._reschedule_after_delay(entry)
                continue

            asyncio.create_task(self._execute_task(entry))

    def _check_misfire(self, entry: TaskEntry, scheduled: ScheduledTask) -> bool:
        """检查是否错过执行（使用队列中的调度时间，避免重算触发器）"""
        if entry.misfire_grace_time is None:
            return False

        elapsed = (datetime.now() - scheduled.next_run_time).total_seconds()
        return elapsed > entry.misfire_grace_time

    def _handle_misfire(self, entry: TaskEntry) -> None:
        """处理错过执行：发布事件、告警、重调度或标记失败"""
        logger.warning(
            f"任务错过执行: {entry.name}({entry.id})",
            _LOG_COMMAND,
        )

        asyncio.create_task(self._emit_missed(entry))

        if isinstance(entry.trigger, DateTrigger):
            entry.status = TaskStatus.FAILED
            logger.error(
                f"一次性任务错过执行时间，标记为失败: {entry.name}({entry.id})",
                _LOG_COMMAND,
            )
        else:
            self._schedule_task(entry)

    async def _emit_missed(self, entry: TaskEntry) -> None:
        """发布错过执行事件并触发告警"""
        await self._emit_event(
            TaskEvent(
                event_type=TaskEventType.TASK_MISSED,
                task_id=entry.id,
                task_name=entry.name,
                group=entry.group,
                trigger_type=entry.trigger_type.value,
            )
        )
        await self._alert_manager.check_missed(
            task_id=entry.id,
            task_name=entry.name,
            group=entry.group,
        )

    def _check_dependencies(self, entry: TaskEntry) -> bool:
        """检查依赖是否满足（增量维护已完成集合，O(deps) 子集判断）"""
        if not entry.dependencies:
            return True
        self._cleanup_completed_tasks()
        return set(entry.dependencies) <= self._completed_tasks.keys()

    async def _execute_task(self, entry: TaskEntry) -> None:
        """执行任务（独立计时器，合并异步回调）"""
        if not self._executor.can_run(entry.id, entry.max_instances):
            # 并发已满：延迟重试而非用过期时间重排，避免热循环
            self._reschedule_after_delay(entry)
            return

        # 独立计时器，避免并发冲突
        start_perf = time.perf_counter()

        await self._emit_event(
            TaskEvent(
                event_type=TaskEventType.TASK_STARTED,
                task_id=entry.id,
                task_name=entry.name,
                group=entry.group,
                trigger_type=entry.trigger_type.value,
            )
        )

        def on_complete(result: ExecutionResult) -> None:
            """任务完成回调（同步，将异步操作合并为一个 create_task）"""
            duration = time.perf_counter() - start_perf
            entry.last_run_time = datetime.now()
            entry.run_count += 1
            success = result.success

            if success:
                if isinstance(entry.trigger, DateTrigger):
                    entry.trigger.mark_executed()
                    entry.status = TaskStatus.COMPLETED
                    self._completed_tasks[entry.id] = time.time()
                else:
                    self._schedule_task(entry)

                event_type = TaskEventType.TASK_FINISHED
                event_data: dict[str, Any] = {
                    "duration": duration, "result": str(result.result),
                }
            else:
                logger.error(
                    f"任务执行失败: {entry.name}({entry.id})",
                    _LOG_COMMAND,
                )
                entry.status = TaskStatus.FAILED
                self._schedule_task(entry)

                event_type = TaskEventType.TASK_FAILED
                event_data = {
                    "duration": duration, "error": str(result.error),
                }

            # 合并所有异步操作为一个 create_task，减少微任务数量
            asyncio.create_task(
                self._post_execute(entry, event_type, event_data, duration, success)
            )

        await self._executor.execute(
            task_id=entry.id,
            func=entry.func,
            max_instances=entry.max_instances,
            args=entry.args,
            kwargs=entry.kwargs,
            on_complete=on_complete,
        )

    async def _emit_event(self, event: TaskEvent) -> None:
        """发布事件并更新事件计数"""
        await self._event_bus.emit(event)
        self._metrics.increment_event_count()

    async def _post_execute(
        self,
        entry: TaskEntry,
        event_type: TaskEventType,
        event_data: dict[str, Any],
        duration: float,
        success: bool,
    ) -> None:
        """执行后统一处理（事件、指标、告警、数据库清理）"""
        try:
            await self._emit_event(
                TaskEvent(
                    event_type=event_type,
                    task_id=entry.id,
                    task_name=entry.name,
                    group=entry.group,
                    data=event_data,
                )
            )

            self._metrics.record_task_execution(
                task_id=entry.id,
                task_name=entry.name,
                group=entry.group,
                success=success,
                duration=duration,
            )

            await self._alert_manager.check_timeout(
                task_id=entry.id,
                task_name=entry.name,
                group=entry.group,
                duration=duration,
            )

            await self._alert_manager.check_long_running(
                task_id=entry.id,
                task_name=entry.name,
                group=entry.group,
                duration=duration,
            )

            if success and isinstance(entry.trigger, DateTrigger):
                await self._cleanup_completed_date_task(entry)

        except Exception as e:
            logger.error(
                f"任务后处理异常: {entry.id}",
                _LOG_COMMAND,
                e=e,
            )

    async def _cleanup_completed_date_task(self, entry: TaskEntry) -> None:
        """
        清理已完成的一次性任务

        对于持久化到数据库的一次性任务，执行完成后需要从数据库删除
        """
        if not entry.save_to_db:
            return

        deleted = await SchedulerJob.delete_job(entry.id)
        if deleted:
            logger.info(
                f"一次性任务执行完成，已从数据库删除: {entry.name}({entry.id})",
                _LOG_COMMAND,
            )

    def _cleanup_completed_tasks(self) -> None:
        """清理过期的已完成任务记录"""
        if not self._completed_tasks:
            return

        cutoff = time.time() - COMPLETED_TASK_TTL
        expired = [tid for tid, ts in self._completed_tasks.items() if ts < cutoff]
        for tid in expired:
            del self._completed_tasks[tid]

    def _get_next_wait_time(self) -> float | None:
        """获取下次等待时间（跳过已失效的队列条目）"""
        while self._priority_queue:
            scheduled = self._priority_queue[0]
            entry = self._tasks.get(scheduled.task_id)

            # 跳过懒删除的过期条目
            if entry is None or entry.version != scheduled.version:
                heapq.heappop(self._priority_queue)
                continue

            wait_seconds = (scheduled.next_run_time - datetime.now()).total_seconds()
            return max(0, wait_seconds)

        return None

    def _update_metrics(self) -> None:
        """更新调度器指标（任务数、队列大小）"""
        total = len(self._tasks)
        paused = sum(
            1 for t in self._tasks.values() if t.status == TaskStatus.PAUSED
        )
        self._metrics.update_scheduler_metrics(
            total_tasks=total,
            running_tasks=total - paused,
            paused_tasks=paused,
            queue_size=len(self._priority_queue),
        )
