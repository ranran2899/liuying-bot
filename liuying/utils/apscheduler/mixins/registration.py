"""
任务注册 Mixin
负责任务的创建、触发器构建和注册
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from liuying.utils.apscheduler.constants import DEFAULT_MISFIRE_GRACE_TIME
from liuying.utils.apscheduler.mixins.base import TaskManagerBaseMixin
from liuying.utils.apscheduler.models import TaskConfig, TaskInfo
from liuying.utils.apscheduler.triggers import (
    BaseTrigger,
    trigger_factory,
)
from liuying.utils.enum import TaskStatus, TriggerType
from liuying.utils.log import logger


class TaskRegistrationMixin(TaskManagerBaseMixin):
    """
    任务注册 Mixin

    提供:
    - 触发器创建(通过 TriggerFactory)
    - 任务注册到管理器
    - 添加 cron/interval/date 三种类型任务
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

    def _create_trigger(
        self,
        trigger_type: str,
        trigger_config: dict[str, Any],
    ) -> BaseTrigger:
        """根据类型和配置创建触发器(委托给 TriggerFactory)

        参数:
            trigger_type: 触发器类型(cron/interval/date)
            trigger_config: 触发器配置

        返回:
            触发器实例

        异常:
            ValueError: 不支持的触发器类型
        """
        return trigger_factory.create(trigger_type, trigger_config)

    def _register_task(self, config: TaskConfig) -> TaskInfo:
        """注册任务到管理器(内存注册,不涉及调度器和数据库)

        参数:
            config: 任务配置对象

        返回:
            任务信息对象

        异常:
            ValueError: 任务已存在且不允许替换
        """
        if config.task_id in self._tasks and not config.replace_existing:
            raise ValueError(
                f"任务 '{config.task_id}' 已存在,"
                f"请使用 replace_existing=True 来替换"
            )

        task_info = TaskInfo(
            id=config.task_id,
            name=config.name,
            trigger_type=config.trigger_type,
            func=config.func,
            group=config.group,
            description=config.description,
            trigger_config=config.trigger_config,
            max_instances=config.max_instances,
            args=config.args,
            kwargs=config.kwargs,
            priority=config.priority,
            dependencies=config.dependencies,
            misfire_grace_time=config.misfire_grace_time,
            status=TaskStatus.RUNNING,
            save_to_db=config.save_to_db,
        )

        self._tasks[config.task_id] = task_info

        if config.group not in self._groups:
            self._groups[config.group] = []
        if config.task_id not in self._groups[config.group]:
            self._groups[config.group].append(config.task_id)

        logger.debug(
            f"注册定时任务: {config.name}({config.task_id}) "
            f"[分组: {config.group}]"
        )
        return task_info

    async def _add_task(self, config: TaskConfig) -> TaskInfo:
        """添加任务的内部实现(注册 + 调度 + 可选持久化)

        参数:
            config: 任务配置对象

        返回:
            任务信息对象
        """
        trigger = self._create_trigger(
            config.trigger_type.value, config.trigger_config
        )

        task_info = self._register_task(config)

        self._scheduler.add_task(
            task_id=config.task_id,
            name=config.name,
            trigger=trigger,
            func=config.func,
            trigger_type=config.trigger_type,
            trigger_config=config.trigger_config,
            args=config.args,
            kwargs=config.kwargs,
            group=config.group,
            priority=config.priority,
            max_instances=config.max_instances,
            misfire_grace_time=config.misfire_grace_time,
            dependencies=config.dependencies,
            description=config.description,
            replace_existing=config.replace_existing,
            save_to_db=config.save_to_db,
        )

        if config.save_to_db:
            await self._save_to_db(
                task_id=config.task_id,
                name=config.name,
                trigger_type=config.trigger_type,
                trigger_config=config.trigger_config,
                group=config.group,
                description=config.description,
                max_instances=config.max_instances,
                args=config.args,
                kwargs=config.kwargs,
                func=config.func,
                priority=config.priority,
            )

        logger.debug(
            f"添加 {config.trigger_type.value} 定时任务: "
            f"{config.name}({config.task_id})"
        )
        return task_info

    async def add_cron_task(
        self,
        task_id: str,
        func: Callable,
        year: int | str | None = None,
        month: int | str | None = None,
        day: int | str | None = None,
        week: int | str | None = None,
        day_of_week: int | str | None = None,
        hour: int | str | None = None,
        minute: int | str | None = None,
        second: int | str | None = None,
        start_date: datetime | str | None = None,
        end_date: datetime | str | None = None,
        timezone: str | None = None,
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
            week: 周数
            day_of_week: 星期几
            hour: 小时
            minute: 分钟
            second: 秒
            start_date: 开始时间
            end_date: 结束时间
            timezone: 时区
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
            year=year, month=month, day=day, week=week,
            day_of_week=day_of_week, hour=hour, minute=minute,
            second=second, start_date=start_date, end_date=end_date,
            timezone=timezone,
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

    async def add_interval_task(
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
        timezone: str | None = None,
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
            timezone: 时区
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
            timezone=timezone, jitter=jitter,
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

    async def add_date_task(
        self,
        task_id: str,
        func: Callable,
        run_date: datetime | str,
        timezone: str | None = None,
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
            timezone: 时区
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
        trigger_config = self._build_trigger_config(
            run_date=run_date, timezone=timezone,
        )
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
