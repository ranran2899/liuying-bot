"""
核心调度器
负责任务调度、优先级管理、依赖关系处理
"""

import asyncio
import bisect
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import heapq
import time
from typing import Any

from liuying.models.scheduler_job import SchedulerJob
from liuying.utils.apscheduler.alert import alert_manager
from liuying.utils.apscheduler.constants import DEFAULT_MISFIRE_GRACE_TIME
from liuying.utils.apscheduler.events import (
    TaskEvent,
    TaskEventType,
    event_bus,
)
from liuying.utils.apscheduler.executor import ExecutionResult, TaskExecutor
from liuying.utils.apscheduler.metrics import (
    metrics_collector,
)
from liuying.utils.apscheduler.models import TaskInfo
from liuying.utils.apscheduler.triggers import BaseTrigger, DateTrigger
from liuying.utils.enum import TaskStatus, TriggerType
from liuying.utils.log import logger

_COMPLETED_TASK_TTL = 86400


def _to_naive_datetime(dt: datetime) -> datetime:
    """将 datetime 转换为 naive datetime（不带时区）"""
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def _get_now() -> datetime:
    """获取当前时间（naive datetime）"""
    return datetime.now()


@dataclass(order=True, slots=True)
class ScheduledTask:
    """调度任务包装类"""

    next_run_time: datetime
    """下次运行时间"""
    task_id: str = field(compare=False)
    """任务ID"""
    priority: int = field(default=0, compare=True)
    """优先级，数值越小优先级越高"""
    version: int = field(default=0, compare=False)
    """版本号，用于懒删除校验"""


@dataclass(slots=True)
class CompletedRecord:
    """已完成任务记录（带 TTL）"""

    task_id: str
    completed_at: float


@dataclass(slots=True)
class TaskEntry(TaskInfo):
    """
    调度器任务条目（继承自统一任务模型）

    在 TaskInfo 基础上添加调度器所需的触发器实例和运行时属性。
    """

    trigger: BaseTrigger = field(default=None, repr=False)
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
        if isinstance(self.trigger, DateTrigger):
            self._cached_next_run_time = self.trigger.run_date
            return
        result = self.trigger.get_next_run_time(self.last_run_time)
        self._cached_next_run_time = result.next_run_time


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
        self._completed_tasks: list[CompletedRecord] = []
        self._completed_times: list[float] = []
        self._completed_ids: set[str] = set()

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
        logger.info("定时任务调度器已启动")

    async def stop(self, wait: bool = True) -> None:
        """停止调度器"""
        self._running = False
        self._wakeup_event.set()

        if self._scheduler_task:
            if wait:
                try:
                    await asyncio.wait_for(self._scheduler_task, timeout=5.0)
                except TimeoutError:
                    self._scheduler_task.cancel()
                    try:
                        await self._scheduler_task
                    except asyncio.CancelledError:
                        pass
            else:
                self._scheduler_task.cancel()

        await self._executor.shutdown()
        logger.info("定时任务调度器已停止")

    def add_task(
        self,
        task_id: str,
        name: str,
        trigger: BaseTrigger,
        func: Callable[..., Any],
        trigger_type: TriggerType,
        trigger_config: dict[str, Any],
        args: tuple | None = None,
        kwargs: dict[str, Any] | None = None,
        group: str = "default",
        priority: int = 10,
        max_instances: int = 1,
        misfire_grace_time: int | None = DEFAULT_MISFIRE_GRACE_TIME,
        dependencies: list[str] | None = None,
        description: str = "",
        replace_existing: bool = False,
        save_to_db: bool = False,
    ) -> TaskEntry:
        """添加任务（含循环依赖检测）"""
        if task_id in self._tasks and not replace_existing:
            raise ValueError(f"任务 '{task_id}' 已存在")

        deps = dependencies or []
        if deps:
            cycle = self._detect_cycle(task_id, deps)
            if cycle:
                raise ValueError(
                    f"检测到循环依赖: {' -> '.join(cycle)}"
                )

        entry = TaskEntry(
            id=task_id, name=name, trigger=trigger, func=func,
            args=args or (), kwargs=kwargs or {}, group=group,
            priority=priority, max_instances=max_instances,
            misfire_grace_time=misfire_grace_time,
            dependencies=deps, description=description,
            trigger_type=trigger_type, trigger_config=trigger_config,
            status=TaskStatus.RUNNING, save_to_db=save_to_db,
        )

        self._tasks[task_id] = entry
        self._schedule_task(entry)
        self._wakeup_event.set()

        logger.debug(f"添加定时任务: {name}({task_id})")
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
                    return path[cycle_start:] + [dep_id]
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
            logger.debug(f"任务 {entry.id} 没有下次运行时间")
            return

        scheduled = ScheduledTask(
            next_run_time=_to_naive_datetime(next_time),
            task_id=entry.id,
            priority=entry.priority,
            version=entry.version,
        )

        heapq.heappush(self._priority_queue, scheduled)
        logger.debug(
            f"任务 {entry.id} 已加入队列, "
            f"下次运行时间: {scheduled.next_run_time}, "
            f"版本: {scheduled.version}"
        )
        self._wakeup_event.set()

    def _reschedule_after_delay(self, entry: TaskEntry, seconds: float = 1.0) -> None:
        """延迟指定秒数后重新调度任务（用于依赖未满足等场景，避免忙等）"""
        next_time = _get_now() + timedelta(seconds=seconds)
        scheduled = ScheduledTask(
            next_run_time=next_time,
            task_id=entry.id,
            priority=entry.priority,
            version=entry.version,
        )
        heapq.heappush(self._priority_queue, scheduled)
        logger.debug(
            f"任务 {entry.id} 将在 {seconds} 秒后重新检查依赖, "
            f"版本: {scheduled.version}"
        )
        self._wakeup_event.set()

    def remove_task(self, task_id: str) -> bool:
        """移除任务（懒删除：递增版本号使旧条目自动失效）"""
        if task_id not in self._tasks:
            return False

        # 递增版本号，队列中旧版本条目将被自动跳过
        self._tasks[task_id].bump_version()
        del self._tasks[task_id]

        logger.debug(f"移除定时任务: {task_id}")
        return True

    def pause_task(self, task_id: str) -> bool:
        """暂停任务（懒删除：递增版本号使旧条目失效）"""
        if task_id not in self._tasks:
            return False

        self._tasks[task_id].status = TaskStatus.PAUSED
        self._tasks[task_id].bump_version()

        return True

    def resume_task(self, task_id: str) -> bool:
        """恢复任务"""
        if task_id not in self._tasks:
            return False

        entry = self._tasks[task_id]
        entry.status = TaskStatus.RUNNING
        self._schedule_task(entry)
        self._wakeup_event.set()

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
        misfire_grace_time: int | None | bool = None,
    ) -> bool:
        """修改任务（仅允许显式字段，避免 **kwargs 滥用）"""
        if task_id not in self._tasks:
            return False

        entry = self._tasks[task_id]

        match trigger:
            case BaseTrigger():
                entry.trigger = trigger

        match trigger_type:
            case TriggerType():
                entry.trigger_type = trigger_type

        if trigger_config:
            entry.trigger_config = trigger_config
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
        if misfire_grace_time is not None and misfire_grace_time is not False:
            entry.misfire_grace_time = misfire_grace_time

        entry.bump_version()

        if entry.status == TaskStatus.RUNNING:
            self._schedule_task(entry)
            self._wakeup_event.set()

        return True

    def run_task_now(self, task_id: str) -> bool:
        """立即执行任务"""
        if task_id not in self._tasks:
            return False

        entry = self._tasks[task_id]

        scheduled = ScheduledTask(
            next_run_time=_get_now(),
            task_id=entry.id,
            priority=-1000,
            version=entry.version,
        )

        heapq.heappush(self._priority_queue, scheduled)
        self._wakeup_event.set()

        return True

    def get_task(self, task_id: str) -> TaskEntry | None:
        """获取任务"""
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> list[TaskEntry]:
        """获取所有任务"""
        return list(self._tasks.values())

    async def _run_loop(self) -> None:
        """调度循环"""
        logger.debug("调度循环开始运行")
        while self._running:
            try:
                await self._process_tasks()

                wait_time = self._get_next_wait_time()
                match wait_time:
                    case None:
                        await self._wakeup_event.wait()
                        self._wakeup_event.clear()
                    case wait_time if wait_time > 0:
                        try:
                            await asyncio.wait_for(
                                self._wakeup_event.wait(),
                                timeout=wait_time,
                            )
                            self._wakeup_event.clear()
                        except TimeoutError:
                            pass

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("调度循环异常", e=e)
                await asyncio.sleep(1)

    async def _process_tasks(self) -> None:
        """处理到期任务（支持批量弹出同一秒内的多个任务）"""
        while self._priority_queue:
            now = _get_now()
            scheduled = self._priority_queue[0]

            if scheduled.next_run_time > now:
                break

            heapq.heappop(self._priority_queue)

            entry = self._tasks.get(scheduled.task_id)

            # 懒删除校验：版本不匹配则跳过
            if entry is None:
                continue

            if entry.version != scheduled.version:
                continue

            if entry.status != TaskStatus.RUNNING:
                logger.debug(
                    f"任务 {scheduled.task_id} 状态不是 RUNNING: {entry.status}"
                )
                continue

            if self._check_misfire(entry, scheduled, now):
                logger.warning(f"任务错过执行: {entry.name}({entry.id})")
                if isinstance(entry.trigger, DateTrigger):
                    entry.status = TaskStatus.FAILED
                    logger.error(
                        f"一次性任务错过执行时间，标记为失败: "
                        f"{entry.name}({entry.id})"
                    )
                else:
                    self._schedule_task(entry)
                continue

            if not self._check_dependencies(entry):
                logger.debug(f"任务依赖未满足: {entry.name}({entry.id})")
                self._reschedule_after_delay(entry, seconds=1)
                continue

            logger.debug(f"开始执行任务: {entry.name}({entry.id})")
            asyncio.create_task(self._execute_task(entry))

    def _check_misfire(
        self, entry: TaskEntry, scheduled: ScheduledTask, now: datetime
    ) -> bool:
        """检查是否错过执行（使用队列中的调度时间，避免重算触发器）"""
        if entry.misfire_grace_time is None:
            return False

        elapsed = (now - scheduled.next_run_time).total_seconds()
        return elapsed > entry.misfire_grace_time

    def _check_dependencies(self, entry: TaskEntry) -> bool:
        """检查依赖是否满足（增量维护已完成集合，O(deps) 子集判断）"""
        self._cleanup_completed_tasks()
        if not entry.dependencies:
            return True
        return set(entry.dependencies) <= self._completed_ids

    async def _execute_task(self, entry: TaskEntry) -> None:
        """执行任务（独立计时器，合并异步回调）"""
        if not self._executor.can_run(entry.id, entry.max_instances):
            logger.debug(f"任务达到最大并发数: {entry.name}({entry.id})")
            self._schedule_task(entry)
            return

        # 独立计时器，避免并发冲突
        start_perf = time.perf_counter()

        await self._event_bus.emit(
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
            entry.last_run_time = _get_now()
            entry.run_count += 1
            success = result.success

            if success:
                logger.debug(f"任务执行成功: {entry.name}({entry.id})")

                if isinstance(entry.trigger, DateTrigger):
                    entry.trigger.mark_executed()
                    entry.status = TaskStatus.COMPLETED
                    self._add_completed_record(entry.id)
                else:
                    self._schedule_task(entry)

                event_type = TaskEventType.TASK_FINISHED
                event_data: dict[str, Any] = {
                    "duration": duration, "result": str(result.result),
                }
            else:
                logger.error(f"任务执行失败: {entry.name}({entry.id})")
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

    def _add_completed_record(self, task_id: str) -> None:
        """添加已完成任务记录（同步维护三个并行结构）"""
        now_ts = time.time()
        self._completed_tasks.append(CompletedRecord(task_id, now_ts))
        self._completed_times.append(now_ts)
        self._completed_ids.add(task_id)

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
            await self._event_bus.emit(
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

            await self._check_and_alert(entry, duration, success)

            if success and isinstance(entry.trigger, DateTrigger):
                await self._cleanup_completed_date_task(entry)

        except Exception as e:
            logger.error(f"任务后处理异常: {entry.id}", e=e)

    async def _cleanup_completed_date_task(self, entry: TaskEntry) -> None:
        """
        清理已完成的一次性任务

        对于持久化到数据库的一次性任务，执行完成后需要从数据库删除
        """
        if not entry.save_to_db:
            return

        try:
            deleted = await SchedulerJob.delete_job(entry.id)
            if deleted:
                logger.info(
                    f"一次性任务执行完成，已从数据库删除: {entry.name}({entry.id})"
                )
            else:
                logger.debug(
                    f"一次性任务未在数据库中找到: {entry.name}({entry.id})"
                )
        except Exception as e:
            logger.error(
                f"删除一次性任务数据库记录失败: {entry.name}({entry.id})",
                e=e
            )

    async def _check_and_alert(
        self,
        entry: TaskEntry,
        duration: float,
        success: bool,
    ) -> None:
        """检查并触发告警"""
        try:
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
        except Exception as e:
            logger.error(f"告警检查异常: {entry.id}", e=e)

    def _cleanup_completed_tasks(self) -> None:
        """清理过期的已完成任务记录（bisect 二分查找 + 平行时间列表）"""
        if not self._completed_tasks:
            return

        cutoff = time.time() - _COMPLETED_TASK_TTL
        idx = bisect.bisect_left(self._completed_times, cutoff)

        if idx > 0:
            del self._completed_tasks[:idx]
            del self._completed_times[:idx]
            self._completed_ids = {r.task_id for r in self._completed_tasks}

    def _get_next_wait_time(self) -> float | None:
        """获取下次等待时间（跳过已失效的队列条目）"""
        while self._priority_queue:
            scheduled = self._priority_queue[0]
            entry = self._tasks.get(scheduled.task_id)

            # 跳过懒删除的过期条目
            if entry is None or entry.version != scheduled.version:
                heapq.heappop(self._priority_queue)
                continue

            now = _get_now()
            wait_seconds = (scheduled.next_run_time - now).total_seconds()
            return max(0, wait_seconds)

        return None

    def mark_dependency_completed(self, task_id: str) -> None:
        """标记依赖任务已完成"""
        self._add_completed_record(task_id)
