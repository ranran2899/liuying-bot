"""SocialTrigger框架

把"什么时候触发"（cron/interval）与"触发后做什么"（handler）
解耦：触发器以 name/调度类型/参数声明式注册，由注册表统一
挂到 APScheduler；启用与否由注册方在注册时决定。

注册表模式：通过 social_trigger_registry 单例注册触发器，
setup_to_scheduler() 将所有触发器注册到调度。
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from liuying.services.apscheduler import task_manager
from liuying.utils.log import logger

__all__ = [
    "ScheduleKind",
    "SocialTrigger",
    "SocialTriggerRegistry",
    "social_trigger_registry",
]


class ScheduleKind(StrEnum):
    """触发器调度类型枚举

    成员即 str，与注册时传入的字符串字面量兼容。
    """

    CRON = "cron"
    INTERVAL = "interval"


@dataclass(slots=True)
class SocialTrigger:
    """单个主动社交场景的触发器配置

    schedule_kind/schedule_args决定调度方式：
    - kind="cron" + args={"hour": 8, "minute": 0}
    - kind="interval" + args={"minutes": 30}

    Attributes:
        name: 触发器名称（同时作为task_id后缀）
        handler: 无参数异步处理函数，内部自行遍历目标群/用户
        schedule_kind: 调度类型（cron/interval）
        schedule_args: 调度参数
    """

    name: str
    handler: Callable[[], Awaitable[None]]
    schedule_kind: str = ScheduleKind.CRON
    schedule_args: dict[str, Any] = field(
        default_factory=dict
    )


class SocialTriggerRegistry:
    """SocialTrigger注册表

    集中管理所有主动社交场景触发器的注册与查询。
    setup_to_scheduler 将所有已注册触发器按 schedule_kind
    注册到 APScheduler；启用判断由注册方在 register 前完成。
    """

    def __init__(self) -> None:
        """初始化空注册表"""
        self._registry: dict[str, SocialTrigger] = {}

    def register(self, trigger: SocialTrigger) -> None:
        """注册一个SocialTrigger

        重名会覆盖（便于热重载）。

        参数:
            trigger: 触发器配置
        """
        self._registry[trigger.name] = trigger

    def clear(self) -> None:
        """清空注册表（重新注册前调用，避免重启叠加）"""
        self._registry.clear()

    def list(self) -> list[SocialTrigger]:
        """列出所有已注册的触发器

        返回:
            list[SocialTrigger]: 触发器列表
        """
        return list(self._registry.values())

    async def setup_to_scheduler(self) -> int:
        """将所有触发器注册到APScheduler调度

        按schedule_kind调用task_manager.add_cron /
        add_interval，任务体统一兜底异常。

        返回:
            int: 成功注册的触发器数量
        """
        count = 0
        for trigger in self.list():
            if trigger.schedule_kind not in (
                ScheduleKind.CRON,
                ScheduleKind.INTERVAL,
            ):
                logger.debug(
                    f"未知调度类型 {trigger.schedule_kind}，"
                    f"跳过触发器 {trigger.name}",
                    command="AI",
                )
                continue
            wrapped = self._wrap_handler(trigger.handler)
            task_id = f"ai_social_{trigger.name}"
            try:
                if trigger.schedule_kind == ScheduleKind.CRON:
                    await task_manager.add_cron(
                        task_id=task_id,
                        func=wrapped,
                        **trigger.schedule_args,
                    )
                else:
                    await task_manager.add_interval(
                        task_id=task_id,
                        func=wrapped,
                        **trigger.schedule_args,
                    )
                count += 1
            except Exception as e:
                logger.warning(
                    f"注册触发器 {trigger.name} 失败: {e}",
                    command="AI",
                    e=e,
                )
        return count

    @staticmethod
    def _wrap_handler(
        handler: Callable[[], Awaitable[None]],
    ) -> Callable[[], Awaitable[None]]:
        """包装任务体：统一兜底异常

        单个社交场景异常不应影响调度器中其他任务的执行。

        参数:
            handler: 触发器处理函数

        返回:
            带兜底的无参数协程函数
        """

        async def _wrapped() -> None:
            try:
                await handler()
            except Exception as e:
                logger.warning(
                    f"社交触发器执行失败: {e}",
                    command="AI",
                    e=e,
                )

        return _wrapped


social_trigger_registry = SocialTriggerRegistry()
"""社交触发器注册表单例"""
