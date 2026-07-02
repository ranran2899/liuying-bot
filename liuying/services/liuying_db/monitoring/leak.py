"""连接泄漏检测器"""

import asyncio
from collections.abc import Callable
import time

from liuying.utils.log import logger

from ..config import LOG_COMMAND
from ._utils import run_monitor_loop, stop_monitor_task


class ConnectionLeakDetector:
    """连接泄漏检测器"""

    __slots__ = (
        "_connections",
        "_leak_callbacks",
        "_monitor_task",
        "check_interval",
        "leak_threshold",
        "max_leak_age",
    )

    def __init__(
        self,
        leak_threshold: float = 30.0,
        check_interval: float = 60.0,
        max_leak_age: float = 300.0,
    ):
        """初始化连接泄漏检测器

        参数:
            leak_threshold: 连接占用超过此时间视为潜在泄漏（秒）
            check_interval: 检查间隔（秒）
            max_leak_age: 最大泄漏时间，超过此时间强制告警（秒）
        """
        self.leak_threshold = leak_threshold
        self.check_interval = check_interval
        self.max_leak_age = max_leak_age
        self._connections: dict[int, tuple[str, float, str]] = {}
        self._monitor_task: asyncio.Task | None = None
        self._leak_callbacks: list[Callable[[str, int, float], None]] = []

    def register_session(
        self, db_name: str, session_id: int, trace_info: str = ""
    ) -> None:
        """注册会话连接

        参数:
            db_name: 数据库名称
            session_id: 会话ID
            trace_info: 追踪信息
        """
        self._connections[session_id] = (db_name, time.time(), trace_info)

    def unregister_session(self, session_id: int) -> None:
        """注销会话连接

        参数:
            session_id: 会话ID
        """
        self._connections.pop(session_id, None)

    def detect_leaks(self) -> list[tuple[str, int, float, str]]:
        """检测泄漏的连接

        返回:
            list: 泄漏连接列表 [(db_name, session_id, 占用时间, 追踪信息)]
        """
        now = time.time()
        return [
            (db_name, sid, now - t, info)
            for sid, (db_name, t, info) in list(self._connections.items())
            if now - t > self.leak_threshold
        ]

    def add_leak_callback(
        self, callback: Callable[[str, int, float], None]
    ) -> None:
        """添加泄漏回调函数

        参数:
            callback: 回调函数，参数为 (db_name, session_id, 占用时间)
        """
        self._leak_callbacks.append(callback)

    def _check_leaks(self):
        """执行泄漏检查并触发回调"""
        for db_name, session_id, age, trace_info in self.detect_leaks():
            logger.warning(
                f"检测到潜在连接泄漏: 数据库={db_name}, "
                f"会话ID={session_id}, 占用时间={age:.1f}秒, 追踪={trace_info}",
                LOG_COMMAND,
            )
            for callback in self._leak_callbacks:
                try:
                    callback(db_name, session_id, age)
                except Exception as e:
                    logger.error(f"泄漏回调执行失败: {e}", LOG_COMMAND)

    async def start_monitoring(self) -> None:
        """启动泄漏监控"""
        if self._monitor_task and not self._monitor_task.done():
            return
        self._monitor_task = asyncio.create_task(
            run_monitor_loop(self.check_interval, self._check_leaks)
        )
        logger.info("连接泄漏监控已启动", LOG_COMMAND)

    async def stop_monitoring(self) -> None:
        """停止泄漏监控"""
        await stop_monitor_task(self._monitor_task)
        self._monitor_task = None
        logger.info("连接泄漏监控已停止", LOG_COMMAND)

    def get_stats(self) -> dict:
        """获取泄漏检测统计信息

        返回:
            dict: 统计信息
        """
        now = time.time()
        ages = [now - t for _, t, _ in self._connections.values()]
        return {
            "active_connections": len(self._connections),
            "potential_leaks": len(self.detect_leaks()),
            "avg_connection_age": sum(ages) / len(ages) if ages else 0,
            "max_connection_age": max(ages) if ages else 0,
            "leak_threshold": self.leak_threshold,
        }


leak_detector = ConnectionLeakDetector()
