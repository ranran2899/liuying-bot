"""
任务装饰器 Mixin
提供装饰器方式注册定时任务
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from liuying.utils.apscheduler.constants import DEFAULT_MISFIRE_GRACE_TIME
from liuying.utils.apscheduler.mixins.base import TaskManagerBaseMixin
from liuying.utils.apscheduler.mixins.registration import (
    TaskRegistrationMixin,
)
from liuying.utils.apscheduler.models import TaskConfig
from liuying.utils.enum import TriggerType

_pending_tasks: list[tuple[str, Callable[..., Any], TaskConfig]] = []


class TaskDecoratorMixin(TaskManagerBaseMixin):
    """
    任务装饰器 Mixin

    提供:
    - @cron_task 装饰器
    - @interval_task 装饰器
    - @date_task 装饰器

    装饰器构造 TaskConfig 后存入 _pending_tasks,
    由 register_pending_tasks 在启动时统一注册。
    """

    def cron_task(
        self,
        task_id: str,
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
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """装饰器方式添加 cron 定时任务

        参数:
            task_id: 任务唯一标识
            year: 年份
            month: 月份
            day: 日期
            week: 周数
            day_of_week: 星期几 (0=周日 或 mon,tue 等)
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
            装饰器函数
        """

        def decorator(
            func: Callable[..., Any],
        ) -> Callable[..., Any]:
            trigger_config = TaskRegistrationMixin._build_trigger_config(
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
            _pending_tasks.append(("cron", func, config))
            return func

        return decorator

    def interval_task(
        self,
        task_id: str,
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
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """装饰器方式添加固定间隔定时任务

        参数:
            task_id: 任务唯一标识
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
            装饰器函数
        """

        def decorator(
            func: Callable[..., Any],
        ) -> Callable[..., Any]:
            trigger_config = TaskRegistrationMixin._build_trigger_config(
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
            _pending_tasks.append(("interval", func, config))
            return func

        return decorator

    def date_task(
        self,
        task_id: str,
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
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """装饰器方式添加一次性定时任务

        参数:
            task_id: 任务唯一标识
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
            装饰器函数
        """

        def decorator(
            func: Callable[..., Any],
        ) -> Callable[..., Any]:
            trigger_config = TaskRegistrationMixin._build_trigger_config(
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
            _pending_tasks.append(("date", func, config))
            return func

        return decorator
