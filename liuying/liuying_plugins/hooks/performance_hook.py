import asyncio
from collections import defaultdict
from contextlib import suppress
from dataclasses import dataclass
import time
from typing import ClassVar

from nonebot.adapters import Bot, Event
from nonebot.matcher import Matcher
from nonebot.message import run_postprocessor, run_preprocessor
from nonebot.typing import T_State
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.config import Config
from liuying.models._log.performance_log import PerformanceLog
from liuying.utils.enum import PluginType
from liuying.utils.log import logger

from .auth.utils import get_group_channel_ids

Config.add_plugin_config(
    "hook",
    "PERFORMANCE_MONITOR_ENABLE",
    True,
    help="是否启用性能监控",
    default_value=True,
    type=bool,
)

Config.add_plugin_config(
    "hook",
    "PERFORMANCE_SLOW_THRESHOLD",
    3.0,
    help="慢命令阈值（秒）",
    default_value=3.0,
    type=float,
)

Config.add_plugin_config(
    "hook",
    "PERFORMANCE_LOG_TO_DB",
    False,
    help="是否记录性能日志到数据库",
    default_value=False,
    type=bool,
)

Config.add_plugin_config(
    "hook",
    "PERFORMANCE_ALERT_THRESHOLD",
    10.0,
    help="性能告警阈值（秒）",
    default_value=10.0,
    type=float,
)

LOG_COMMAND = "PerformanceHook"

_STATE_KEY = "_performance_start_time"
_HOOK_TIME_KEY = "_performance_hook_time"


@dataclass(slots=True)
class PerformanceStats:
    """性能统计数据"""

    total_count: int = 0
    total_time: float = 0.0
    max_time: float = 0.0
    min_time: float = float("inf")
    error_count: int = 0
    slow_count: int = 0


class PerformanceMonitor:
    """性能监控器"""

    _stats: ClassVar[dict[str, PerformanceStats]] = defaultdict(PerformanceStats)
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()
    _alert_cooldown: ClassVar[dict[str, float]] = {}
    _alert_cd: ClassVar[float] = 300.0

    @classmethod
    def record(
        cls,
        module: str,
        execute_time: float,
        hook_time: float,
        is_error: bool = False,
    ):
        """记录性能数据

        参数:
            module: 模块名
            execute_time: 执行时间
            hook_time: Hook时间
            is_error: 是否错误
        """
        stats = cls._stats[module]
        stats.total_count += 1
        stats.total_time += execute_time
        stats.max_time = max(stats.max_time, execute_time)
        stats.min_time = min(stats.min_time, execute_time)
        if is_error:
            stats.error_count += 1

        threshold = Config.get_config("hook", "PERFORMANCE_SLOW_THRESHOLD") or 3.0
        if execute_time > threshold:
            stats.slow_count += 1

    @classmethod
    def get_stats(cls, module: str | None = None) -> dict:
        """获取统计数据

        参数:
            module: 模块名，为空时返回所有

        返回:
            dict: 统计数据
        """
        if module:
            stats = cls._stats.get(module)
            if not stats:
                return {}
            return {
                "count": stats.total_count,
                "avg_time": stats.total_time / stats.total_count
                if stats.total_count
                else 0,
                "max_time": stats.max_time,
                "min_time": stats.min_time if stats.min_time != float("inf") else 0,
                "error_count": stats.error_count,
                "slow_count": stats.slow_count,
            }

        return {
            name: {
                "count": s.total_count,
                "avg_time": s.total_time / s.total_count if s.total_count else 0,
                "max_time": s.max_time,
                "min_time": s.min_time if s.min_time != float("inf") else 0,
                "error_count": s.error_count,
                "slow_count": s.slow_count,
            }
            for name, s in cls._stats.items()
        }

    @classmethod
    def reset_stats(cls, module: str | None = None):
        """重置统计数据

        参数:
            module: 模块名，为空时重置所有
        """
        if module:
            cls._stats.pop(module, None)
        else:
            cls._stats.clear()

    @classmethod
    async def check_alert(cls, module: str, execute_time: float) -> bool:
        """检查是否需要告警

        参数:
            module: 模块名
            execute_time: 执行时间

        返回:
            bool: 是否需要告警
        """
        threshold = Config.get_config("hook", "PERFORMANCE_ALERT_THRESHOLD") or 10.0
        if execute_time <= threshold:
            return False

        current_time = time.time()
        last_alert = cls._alert_cooldown.get(module, 0)
        if current_time - last_alert < cls._alert_cd:
            return False

        cls._alert_cooldown[module] = current_time
        return True


@run_preprocessor
async def _(
    matcher: Matcher,
    bot: Bot,
    event: Event,
    state: T_State,
    session: Uninfo,
):
    """性能监控预处理"""
    if not Config.get_config("hook", "PERFORMANCE_MONITOR_ENABLE"):
        return

    if plugin := matcher.plugin:
        if metadata := plugin.metadata:
            extra = metadata.extra
            if extra.get("plugin_type") in {
                PluginType.HIDDEN,
                PluginType.DEPENDANT,
            }:
                return

    state[_STATE_KEY] = time.time()
    state[_HOOK_TIME_KEY] = 0.0


@run_postprocessor
async def _(
    matcher: Matcher,
    exception: Exception | None,
    bot: Bot,
    event: Event,
    session: Uninfo,
    state: T_State,
):
    """性能监控后处理"""
    if not Config.get_config("hook", "PERFORMANCE_MONITOR_ENABLE"):
        return

    start_time = state.get(_STATE_KEY)
    if not start_time:
        return

    module = matcher.plugin_name or "unknown"
    execute_time = time.time() - start_time
    hook_time = state.get(_HOOK_TIME_KEY, 0.0)
    is_error = exception is not None

    PerformanceMonitor.record(module, execute_time, hook_time, is_error)

    slow_threshold = Config.get_config("hook", "PERFORMANCE_SLOW_THRESHOLD") or 3.0
    if execute_time > slow_threshold:
        logger.warning(
            f"慢命令检测: {module}, 耗时: {execute_time:.3f}s",
            LOG_COMMAND,
            session=session,
        )

    if await PerformanceMonitor.check_alert(module, execute_time):
        logger.error(
            f"性能告警: {module} 执行时间过长 ({execute_time:.3f}s)，请检查优化",
            LOG_COMMAND,
            session=session,
        )

    if Config.get_config("hook", "PERFORMANCE_LOG_TO_DB"):
        ids = get_group_channel_ids(session)
        with suppress(Exception):
            await PerformanceLog.add_log(
                module=module,
                user_id=session.user.id,
                group_id=ids.group_id,
                execute_time=execute_time,
                hook_time=hook_time,
                status=1 if is_error else 0,
                error_msg=str(exception)[:500] if exception else None,
            )
