"""系统信息路由

提供运行环境信息：Python/OS 版本、CPU/内存/磁盘占用、进程信息、运行时长。
依赖 psutil。
"""

import os
import platform
import sys
import time
from datetime import datetime, timedelta
from typing import Any

import psutil

from fastapi import APIRouter

__all__ = ["build_system_router"]

_START_TIME = time.time()
"""模块导入时间，近似作为进程启动时间用于运行时长估算"""


def _humanize_duration(seconds: float) -> str:
    """将秒数格式化为人类可读的运行时长"""
    delta = timedelta(seconds=int(seconds))
    days = delta.days
    hours, rem = divmod(delta.seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if days > 0:
        return f"{days}d {hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def build_system_router() -> APIRouter:
    """构建系统信息路由"""
    router = APIRouter(prefix="/system", tags=["WebUI-系统信息"])

    @router.get("")
    async def system_info() -> dict[str, Any]:
        """获取运行环境系统信息"""
        from liuying.utils.bot.version import BotVersionInfo
        from liuying.configs.config import BotConfig

        version = await BotVersionInfo.get_version()
        bot_name = getattr(BotConfig, "self_nickname", "") or "流萤"

        vm = psutil.virtual_memory()
        disk = psutil.disk_usage(os.getcwd())
        proc = psutil.Process()
        cpu_percent = psutil.cpu_percent(interval=None)

        uptime = time.time() - _START_TIME
        return {
            "bot_name": bot_name,
            "bot_version": version,
            "python_version": sys.version.split()[0],
            "platform": platform.system(),
            "os_release": platform.release(),
            "hostname": platform.node(),
            "cpu_percent": round(cpu_percent, 1),
            "cpu_count": psutil.cpu_count(logical=True) or 0,
            "memory_total": vm.total,
            "memory_used": vm.used,
            "memory_percent": round(vm.percent, 1),
            "disk_total": disk.total,
            "disk_used": disk.used,
            "disk_percent": round(disk.percent, 1),
            "process_pid": proc.pid,
            "process_memory_rss": proc.memory_info().rss,
            "process_threads": proc.num_threads(),
            "uptime_seconds": round(uptime, 1),
            "uptime_text": _humanize_duration(uptime),
            "timestamp": datetime.now().isoformat(),
        }

    @router.get("/process")
    async def process_info() -> dict[str, Any]:
        """获取当前进程详细信息"""
        proc = psutil.Process()
        create_time = datetime.fromtimestamp(proc.create_time()).isoformat()
        with proc.oneshot():
            info = {
                "pid": proc.pid,
                "name": proc.name(),
                "create_time": create_time,
                "cpu_percent": proc.cpu_percent(interval=None),
                "memory_rss": proc.memory_info().rss,
                "memory_vms": proc.memory_info().vms,
                "threads": proc.num_threads(),
                "status": proc.status(),
                "exe": proc.exe() or "",
                "cwd": proc.cwd(),
            }
        info["connections"] = len(proc.connections(kind="inet"))
        return info

    return router
