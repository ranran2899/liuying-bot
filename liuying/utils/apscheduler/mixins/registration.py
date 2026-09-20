"""
任务注册 Mixin

负责任务的创建、触发器构建和注册，
提供类接口(add_cron/add_interval/add_date)与装饰器两种等价方式。
装饰器构造 TaskConfig 暂存到 _pending_tasks，
由 register_pending_tasks 在启动时统一注册。
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from liuying.utils.enum import TriggerType
from liuying.utils.log import logger

from ..constants import DEFAULT_MISFIRE_GRACE_TIME
from ..models import TaskConfig, TaskInfo
from ..triggers import trigger_factory
from .base import TaskManagerBaseMixin

_LOG_COMMAND = "SchedulerRegistration"

_pending_tasks: list[TaskConfig] = []
"""装饰器暂存的任务配置，由 register_pending_tasks 在启动时统一注册"""


class TaskRegistrationMixin(TaskManagerBaseMixin):
    """
    任务注册 Mixin

    提供:
    - 触发器创建(委托给 TriggerFactory)
    - 任务注册到管理器与调度器(TaskEntry 单一数据源)
    - cron/interval/date 三种类型任务的类接口与装饰器
    """

    @staticmethod
    def _build_trigger_config(**kwargs: Any) -> dict[str, Any]:
        """构造触发器配置(过滤 None 值)

        参数:
            **kwargs: 触发器字段

        返回:
            过滤 None 后的配置字典
        """
        return {k: v for k, v in kwargs.items() if v is not None}

    async def _add_task(
        self, config: TaskConfig, *, save_to_db: bool | None = None
    ) -> TaskInfo:
        """添加任务的内部实现(注册 + 调度 + 可选持久化)

        调度器创建的 TaskEntry 同时作为管理器层的任务信息，
        避免双仓库状态同步。

        参数:
            config: 任务配置对象
            save_to_db: 是否持久化，None 表示沿用 config.save_to_db

        返回:
            任务信息对象
        """
        trigger = trigger_factory.create(
            config.trigger_type.value, config.trigger_config
        )
        # 调度器创建 TaskEntry 并写入共享任务仓库，管理器直接持有同一实例
        task_info = self._scheduler.add_task(config, trigger)

        group_tasks = self._groups.setdefault(config.group, [])
        if config.task_id not in group_tasks:
            group_tasks.append(config.task_id)

        persist = config.save_to_db if save_to_db is None else save_to_db
        if persist:
            await self._save_to_db(config)

        logger.debug(
            f"添加 {config.trigger_type.value} 定时任务: "
            f"{config.name}({config.task_id}) [分组: {config.group}]",
            _LOG_COMMAND,
        )
        return task_info

    async def add_cron(
        self,
        task_id: str,
        func: Callable,
        year: int | str | None = None,
        month: int | str | None = None,
        day: int | str | None = None,
        day_of_week: int | str | None = None,
        hour: int | str | None = None,
        minute: int | str | None = None,
        second: int | str | None = None,
        start_date: datetime | str | None = None,
        end_date: datetime | str | None = None,
        name: str | None = None,
        group: str = "default",
        description: str = "",
        max_instances: int = 1,
        args: tuple | None = None,
        kwargs: dict[str, Any] | None = None,
        priority: int = 10,
        dependencies: list[str] | None = None,
        replace_existing: bool = False,
        save_to_db: bool = False,
        misfire_grace_time: int = DEFAULT_MISFIRE_GRACE_TIME,
    ) -> TaskInfo:
        """添加 cron 表达式定时任务

        参数:
            task_id: 任务唯一标识
            func: 任务执行函数
            year: 年份
            month: 月份
            day: 日期
            day_of_week: 星期几
            hour: 小时
            minute: 分钟
            second: 秒
            start_date: 开始时间
            end_date: 结束时间
            name: 任务名称
            group: 任务分组
            description: 任务描述
            max_instances: 最大并发实例数
            args: 任务位置参数
            kwargs: 任务关键字参数
            priority: 任务优先级
            dependencies: 依赖的任务ID列表
            replace_existing: 是否替换已存在的任务
            save_to_db: 是否保存到数据库
            misfire_grace_time: 错过执行的宽限时间

        返回:
            任务信息对象
        """
        trigger_config = self._build_trigger_config(
            year=year, month=month, day=day,
            day_of_week=day_of_week, hour=hour, minute=minute,
            second=second, start_date=start_date, end_date=end_date,
        )
        config = TaskConfig(
            task_id=task_id, name=name or task_id,
            trigger_type=TriggerType.CRON, func=func,
            trigger_config=trigger_config, group=group,
            description=description, max_instances=max_instances,
            args=args or (), kwargs=kwargs or {},
            priority=priority, dependencies=dependencies or [],
            misfire_grace_time=misfire_grace_time,
            replace_existing=replace_existing, save_to_db=save_to_db,
        )
        return await self._add_task(config)

    async def add_interval(
        self,
        task_id: str,
        func: Callable,
        weeks: int = 0,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        start_date: datetime | str | None = None,
        end_date: datetime | str | None = None,
        jitter: int | None = None,
        name: str | None = None,
        group: str = "default",
        description: str = "",
        max_instances: int = 1,
        args: tuple | None = None,
        kwargs: dict[str, Any] | None = None,
        priority: int = 10,
        dependencies: list[str] | None = None,
        replace_existing: bool = False,
        save_to_db: bool = False,
        misfire_grace_time: int = DEFAULT_MISFIRE_GRACE_TIME,
    ) -> TaskInfo:
        """添加固定时间间隔定时任务

        参数:
            task_id: 任务唯一标识
            func: 任务执行函数
            weeks: 周数
            days: 天数
            hours: 小时数
            minutes: 分钟数
            seconds: 秒数
            start_date: 开始时间
            end_date: 结束时间
            jitter: 随机偏移时间(秒)
            name: 任务名称
            group: 任务分组
            description: 任务描述
            max_instances: 最大并发实例数
            args: 任务位置参数
            kwargs: 任务关键字参数
            priority: 任务优先级
            dependencies: 依赖的任务ID列表
            replace_existing: 是否替换已存在的任务
            save_to_db: 是否保存到数据库
            misfire_grace_time: 错过执行的宽限时间

        返回:
            任务信息对象
        """
        trigger_config = self._build_trigger_config(
            weeks=weeks, days=days, hours=hours, minutes=minutes,
            seconds=seconds, start_date=start_date, end_date=end_date,
            jitter=jitter,
        )
        config = TaskConfig(
            task_id=task_id, name=name or task_id,
            trigger_type=TriggerType.INTERVAL, func=func,
            trigger_config=trigger_config, group=group,
            description=description, max_instances=max_instances,
            args=args or (), kwargs=kwargs or {},
            priority=priority, dependencies=dependencies or [],
            misfire_grace_time=misfire_grace_time,
            replace_existing=replace_existing, save_to_db=save_to_db,
        )
        return await self._add_task(config)

    async def add_date(
        self,
        task_id: str,
        func: Callable,
        run_date: datetime | str,
        name: str | None = None,
        group: str = "default",
        description: str = "",
        max_instances: int = 1,
        args: tuple | None = None,
        kwargs: dict[str, Any] | None = None,
        priority: int = 10,
        dependencies: list[str] | None = None,
        replace_existing: bool = False,
        save_to_db: bool = True,
    ) -> TaskInfo:
        """添加一次性定时任务

        参数:
            task_id: 任务唯一标识
            func: 任务执行函数
            run_date: 执行时间
            name: 任务名称
            group: 任务分组
            description: 任务描述
            max_instances: 最大并发实例数
            args: 任务位置参数
            kwargs: 任务关键字参数
            priority: 任务优先级
            dependencies: 依赖的任务ID列表
            replace_existing: 是否替换已存在的任务
            save_to_db: 是否保存到数据库

        返回:
            任务信息对象
        """
        trigger_config = self._build_trigger_config(run_date=run_date)
        config = TaskConfig(
            task_id=task_id, name=name or task_id,
            trigger_type=TriggerType.DATE, func=func,
            trigger_config=trigger_config, group=group,
            description=description, max_instances=max_instances,
            args=args or (), kwargs=kwargs or {},
            priority=priority, dependencies=dependencies or [],
            misfire_grace_time=None,
            replace_existing=replace_existing, save_to_db=save_to_db,
        )
        return await self._add_task(config)

    def cron(
        self,
        task_id: str,
        year: int | str | None = None,
        month: int | str | None = None,
        day: int | str | None = None,
        day_of_week: int | str | None = None,
        hour: int | str | None = None,
        minute: int | str | None = None,
        second: int | str | None = None,
        start_date: datetime | str | None = None,
        end_date: datetime | str | None = None,
        name: str | None = None,
        group: str = "default",
        description: str = "",
        max_instances: int = 1,
        args: tuple | None = None,
        kwargs: dict[str, Any] | None = None,
        priority: int = 10,
        dependencies: list[str] | None = None,
        replace_existing: bool = False,
        save_to_db: bool = False,
        misfire_grace_time: int = DEFAULT_MISFIRE_GRACE_TIME,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """装饰器方式添加 cron 定时任务(参数同 add_cron)"""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            _pending_tasks.append(
                TaskConfig(
                    task_id=task_id, name=name or task_id,
                    trigger_type=TriggerType.CRON, func=func,
                    trigger_config=self._build_trigger_config(
                        year=year, month=month, day=day,
                        day_of_week=day_of_week, hour=hour, minute=minute,
                        second=second, start_date=start_date, end_date=end_date,
                    ),
                    group=group, description=description,
                    max_instances=max_instances, args=args or (),
                    kwargs=kwargs or {}, priority=priority,
                    dependencies=dependencies or [],
                    misfire_grace_time=misfire_grace_time,
                    replace_existing=replace_existing,
                    save_to_db=save_to_db,
                )
            )
            return func

        return decorator

    def interval(
        self,
        task_id: str,
        weeks: int = 0,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        start_date: datetime | str | None = None,
        end_date: datetime | str | None = None,
        jitter: int | None = None,
        name: str | None = None,
        group: str = "default",
        description: str = "",
        max_instances: int = 1,
        args: tuple | None = None,
        kwargs: dict[str, Any] | None = None,
        priority: int = 10,
        dependencies: list[str] | None = None,
        replace_existing: bool = False,
        save_to_db: bool = False,
        misfire_grace_time: int = DEFAULT_MISFIRE_GRACE_TIME,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """装饰器方式添加固定间隔定时任务(参数同 add_interval)"""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            _pending_tasks.append(
                TaskConfig(
                    task_id=task_id, name=name or task_id,
                    trigger_type=TriggerType.INTERVAL, func=func,
                    trigger_config=self._build_trigger_config(
                        weeks=weeks, days=days, hours=hours, minutes=minutes,
                        seconds=seconds, start_date=start_date, end_date=end_date,
                        jitter=jitter,
                    ),
                    group=group, description=description,
                    max_instances=max_instances, args=args or (),
                    kwargs=kwargs or {}, priority=priority,
                    dependencies=dependencies or [],
                    misfire_grace_time=misfire_grace_time,
                    replace_existing=replace_existing,
                    save_to_db=save_to_db,
                )
            )
            return func

        return decorator

    def date(
        self,
        task_id: str,
        run_date: datetime | str,
        name: str | None = None,
        group: str = "default",
        description: str = "",
        max_instances: int = 1,
        args: tuple | None = None,
        kwargs: dict[str, Any] | None = None,
        priority: int = 10,
        dependencies: list[str] | None = None,
        replace_existing: bool = False,
        save_to_db: bool = True,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """装饰器方式添加一次性定时任务(参数同 add_date)"""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            _pending_tasks.append(
                TaskConfig(
                    task_id=task_id, name=name or task_id,
                    trigger_type=TriggerType.DATE, func=func,
                    trigger_config=self._build_trigger_config(run_date=run_date),
                    group=group, description=description,
                    max_instances=max_instances, args=args or (),
                    kwargs=kwargs or {}, priority=priority,
                    dependencies=dependencies or [],
                    misfire_grace_time=None,
                    replace_existing=replace_existing,
                    save_to_db=save_to_db,
                )
            )
            return func

        return decorator
