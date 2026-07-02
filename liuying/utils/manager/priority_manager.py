"""优先级生命周期管理器"""

from collections.abc import Callable
from typing import ClassVar

import nonebot
from nonebot.utils import is_coroutine_callable

from liuying.utils.enum import PriorityLifecycleType
from liuying.utils.exception import HookPriorityException
from liuying.utils.log import logger

driver = nonebot.get_driver()


class PriorityLifecycle:
    """优先级生命周期管理器"""
    _data: ClassVar[dict[PriorityLifecycleType, dict[int, list[Callable]]]] = {}

    @classmethod
    def add(cls, hook_type: PriorityLifecycleType, func: Callable, priority: int):
        cls._data.setdefault(hook_type, {}).setdefault(priority, []).append(func)

    @classmethod
    def on_startup(cls, *, priority: int):
        """注册启动时执行的优先级钩子

        参数:
            priority: 优先级
        """
        def wrapper(func):
            cls.add(PriorityLifecycleType.STARTUP, func, priority)
            return func
        return wrapper

    @classmethod
    def on_shutdown(cls, *, priority: int):
        """注册关闭时执行的优先级钩子

        参数:
            priority: 优先级
        """
        def wrapper(func):
            cls.add(PriorityLifecycleType.SHUTDOWN, func, priority)
            return func
        return wrapper


async def _execute_priority_hooks(hook_type: PriorityLifecycleType, type_name: str):
    """按优先级执行生命周期钩子

    参数:
        hook_type: 生命周期类型
        type_name: 类型名称（用于日志）
    """
    priority_data = PriorityLifecycle._data.get(hook_type)
    if not priority_data:
        return
    priority_list = sorted(priority_data.keys())
    priority = 0
    try:
        for priority in priority_list:
            for func in priority_data[priority]:
                logger.debug(
                    f"执行优先级 [{priority}] on_{type_name} 方法: "
                    f"{func.__module__}"
                )
                if is_coroutine_callable(func):
                    await func()
                else:
                    func()
    except HookPriorityException as e:
        logger.error(f"打断优先级 [{priority}] on_{type_name} 方法. {type(e)}: {e}")


@driver.on_startup
async def _():
    await _execute_priority_hooks(PriorityLifecycleType.STARTUP, "startup")


@driver.on_shutdown
async def _():
    await _execute_priority_hooks(PriorityLifecycleType.SHUTDOWN, "shutdown")
