"""
高级定时任务接口

完全自主实现的定时任务管理器,支持 cron、interval、date 三种触发器类型,
提供任务持久化、分组管理、暂停恢复等功能。

使用示例:

    # 装饰器方式(推荐)
    from liuying.utils.apscheduler import task_manager

    @task_manager.cron_task("daily_task", hour=0, minute=0)
    async def daily_cleanup():
        print("每日清理")

    @task_manager.interval_task("heartbeat", seconds=10)
    async def heartbeat():
        print("心跳检测")

    # 类接口方式
    async def my_task():
        print("定时任务")

    await task_manager.add_interval_task("task_id", my_task, seconds=30)
    await task_manager.add_cron_task("cron_id", my_task, hour=8, minute=0)
    await task_manager.add_date_task("once_id", my_task, run_date="2026-01-01 00:00:00")

    # 任务管理
    await task_manager.pause_task("task_id")      # 暂停
    await task_manager.resume_task("task_id")     # 恢复
    await task_manager.remove_task("task_id")     # 移除
    task_manager.run_task_now("task_id")          # 立即执行

    # 分组管理
    await task_manager.pause_group("cleanup")
    await task_manager.resume_group("cleanup")
    task_manager.get_tasks_by_group("cleanup")

    # 持久化任务(保存到数据库)
    # 注意: cron 和 interval 任务默认不持久化,一次性任务默认持久化
    await task_manager.add_interval_task(
        "persistent_task", my_task, seconds=30, save_to_db=True
    )
    await task_manager.add_cron_task(
        "persistent_cron", my_task, hour=8, save_to_db=True
    )
"""

from liuying.utils.apscheduler.events import TaskEvent, TaskEventType, event_bus
from liuying.utils.apscheduler.manager import task_manager
from liuying.utils.apscheduler.metrics import metrics_collector
from liuying.utils.apscheduler.models import TaskConfig, TaskInfo

__all__ = [
    "TaskConfig",
    "TaskEvent",
    "TaskEventType",
    "TaskInfo",
    "event_bus",
    "metrics_collector",
    "task_manager",
]
