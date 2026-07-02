"""
高级定时任务管理器
提供统一的定时任务管理功能,支持任务注册、调度执行、周期管理、异常处理等核心功能

主要特性:
- 完全自主实现的定时任务调度器,无外部依赖
- 支持 cron 表达式、固定时间间隔和特定日期时间三种触发器类型
- 提供装饰器和类接口两种使用方式
- 支持任务的添加、删除、修改、暂停、恢复等完整功能
- 支持任务信息查询和分组管理
- 采用单例模式设计,确保全局唯一的任务管理器实例
- 支持任务优先级、依赖关系和失败重试机制
- 支持数据库持久化存储,项目重启后自动恢复任务
"""

from liuying.utils.apscheduler.alert import alert_manager
from liuying.utils.apscheduler.mixins import (
    TaskDecoratorMixin,
    TaskGroupMixin,
    TaskLifecycleMixin,
    TaskPersistenceMixin,
    TaskQueryMixin,
    TaskRegistrationMixin,
)
from liuying.utils.apscheduler.mixins.decorator import _pending_tasks
from liuying.utils.apscheduler.scheduler import Scheduler
from liuying.utils.log import logger
from liuying.utils.manager.priority_manager import PriorityLifecycle


class TaskManager(
    TaskRegistrationMixin,
    TaskLifecycleMixin,
    TaskGroupMixin,
    TaskQueryMixin,
    TaskDecoratorMixin,
    TaskPersistenceMixin,
):
    """
    高级定时任务管理器

    通过 Mixin 组合实现职责分离,各模块功能:
    - TaskRegistrationMixin: 任务注册与触发器创建
    - TaskLifecycleMixin: 任务生命周期管理(暂停/恢复/移除/修改)
    - TaskGroupMixin: 分组管理
    - TaskQueryMixin: 任务查询
    - TaskDecoratorMixin: 装饰器接口
    - TaskPersistenceMixin: 数据库持久化与恢复
    """

    def __init__(self) -> None:
        self._scheduler = Scheduler()
        self._tasks: dict[str, object] = {}
        self._groups: dict[str, list[str]] = {}
        self._started = False

    async def start(self) -> None:
        """启动任务管理器"""
        if self._started:
            return
        self._started = True
        await self._scheduler.start()
        await alert_manager.start()
        logger.info("定时任务管理器已启动")

    async def stop(self) -> None:
        """停止任务管理器"""
        if not self._started:
            return
        self._started = False
        await alert_manager.stop()
        await self._scheduler.stop()
        logger.info("定时任务管理器已停止")


async def register_pending_tasks(task_manager: TaskManager) -> int:
    """注册所有待处理的装饰器任务

    参数:
        task_manager: 任务管理器实例

    返回:
        成功注册的任务数量
    """
    count = 0
    for _trigger_type, _func, config in _pending_tasks:
        try:
            existing_task = task_manager.get_task(config.task_id)

            if existing_task:
                if existing_task.trigger_type != config.trigger_type:
                    await task_manager.remove_task(
                        config.task_id, delete_from_db=True
                    )
                config.replace_existing = True

            await task_manager._add_task(config)
            count += 1
        except Exception as e:
            logger.error(
                f"注册装饰器任务失败: {config.task_id}", e=e
            )

    _pending_tasks.clear()
    return count


task_manager = TaskManager()


@PriorityLifecycle.on_startup(priority=2)
async def _restore_scheduler_tasks():
    """项目启动时恢复定时任务并注册装饰器任务"""
    await task_manager.start()
    restored_count = await task_manager.restore_tasks()
    pending_count = await register_pending_tasks(task_manager)
    total_count = restored_count + pending_count
    if total_count > 0:
        logger.info(
            f"已加载 {total_count} 个定时任务 "
            f"(数据库: {restored_count}, 装饰器: {pending_count})"
        )


@PriorityLifecycle.on_shutdown(priority=2)
async def _shutdown_scheduler():
    """项目关闭时停止调度器"""
    await task_manager.stop()
