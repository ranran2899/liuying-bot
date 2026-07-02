"""监控工具函数模块，提供通用的监控循环管理功能"""

import asyncio
from collections.abc import Callable


async def stop_monitor_task(task: asyncio.Task | None) -> None:
    """安全停止监控任务

    参数:
        task: 监控任务
    """
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def run_monitor_loop(interval: float, callback: Callable[[], None]) -> None:
    """通用监控循环

    参数:
        interval: 检查间隔（秒）
        callback: 每次循环执行的回调
    """
    while True:
        await asyncio.sleep(interval)
        callback()
