"""
缓存降级管理器

管理Redis缓存降级到内存缓存的检测、触发和恢复。
"""

from collections.abc import Awaitable, Callable
import time
from typing import Any

from liuying.utils.log import logger

from ..config import LOG_COMMAND, CacheMode, cache_config


class DegradeManager:
    """缓存降级管理器

    管理Redis缓存降级到内存缓存的检测、触发和恢复。
    当连续操作失败达到阈值时自动降级，定期异步检测Redis可用性以恢复。
    降级检测复用 BackendManager.test_connection 避免创建临时连接池。
    """

    def __init__(self) -> None:
        self._degraded: bool = False
        self._degrade_reason: str = ""
        self._degrade_time: float = 0.0
        self._consecutive_failures: int = 0

    @property
    def degraded(self) -> bool:
        """获取降级状态

        返回:
            bool: 是否已降级
        """
        return self._degraded

    @property
    def degrade_info(self) -> dict[str, Any]:
        """获取降级信息

        返回:
            dict: 降级信息，包含是否降级、原因和时间
        """
        return {
            "degraded": self._degraded,
            "reason": self._degrade_reason,
            "time": self._degrade_time,
        }

    def record_success(self) -> None:
        """记录操作成功，重置连续失败计数"""
        self._consecutive_failures = 0

    def record_failure(self) -> None:
        """记录操作失败，检测是否需要降级"""
        self._consecutive_failures += 1
        if (
            not self._degraded
            and self._consecutive_failures >= cache_config.degrade_max_failures
        ):
            self.trigger_degrade("连续操作失败达到阈值")

    def trigger_degrade(self, reason: str) -> None:
        """触发降级到内存缓存

        参数:
            reason: 降级原因
        """
        self._degraded = True
        self._degrade_reason = reason
        self._degrade_time = time.time()
        logger.warning(
            f"缓存已降级到内存缓存，原因: {reason}",
            LOG_COMMAND,
        )

    async def try_recover(
        self,
        test_func: Callable[[], Awaitable[bool]] | None = None,
    ) -> bool:
        """尝试从降级状态恢复

        使用外部传入的 test_func（复用 BackendManager 连接）进行检测。
        未提供 test_func 时直接返回False，由调用方负责传入测试函数。

        参数:
            test_func: 连接测试函数，返回True表示连接可用

        返回:
            bool: 是否成功恢复
        """
        if not self._degraded:
            return False
        if cache_config.cache_mode != CacheMode.REDIS:
            self._degraded = False
            return True
        if test_func is None:
            return False

        try:
            if await test_func():
                self._degraded = False
                self._degrade_reason = ""
                self._consecutive_failures = 0
                logger.info("缓存已从降级状态恢复到Redis", LOG_COMMAND)
                return True
        except Exception as e:
            logger.debug("降级恢复检测失败", LOG_COMMAND, e=e)
        return False
