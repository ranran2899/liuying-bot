"""SocialTrigger框架

把"什么时候触发"（cron/interval/event）与"触发后做什么"
（handler）解耦。handler通过SocialContext拿到运行所需的
全部依赖，便于测试和扩展。

注册表模式：通过SocialTriggerRegistry单例注册触发器，
social_trigger_registry.list()列出所有已注册的触发器。
setup_to_scheduler()将所有触发器注册到APScheduler调度。
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from liuying.utils.apscheduler import task_manager
from liuying.utils.log import logger

__all__ = [
    "SocialContext",
    "SocialTrigger",
    "SocialTriggerRegistry",
    "social_trigger_registry",
]


@dataclass(slots=True)
class SocialContext:
    """场景handler收到的运行时上下文

    Attributes:
        group_id: 群组ID
        user_id: 用户ID
        bot: bot实例
        config_get: 配置读取函数
        now: 当前时间
    """

    group_id: str = ""
    user_id: str = ""
    bot: Any = None
    config_get: Callable[[str, Any], Any] = field(
        default_factory=lambda: lambda k, d: d
    )
    now: Any = None


@dataclass(slots=True)
class SocialTrigger:
    """单个主动社交场景的触发器配置

    schedule_kind/schedule_args决定调度方式：
    - kind="cron" + args={"hour": 8, "minute": 0}
    - kind="interval" + args={"minutes": 30}
    - kind="event" 则由消息钩子在适当时机调用handler

    Attributes:
        name: 触发器名称（同时作为task_id）
        handler: 处理函数
        schedule_kind: 调度类型（cron/interval/event）
        schedule_args: 调度参数
        enabled: 启用判断函数
    """

    name: str
    handler: Callable[
        [SocialContext], Awaitable[None]
    ]
    schedule_kind: str = "event"
    schedule_args: dict[str, Any] = field(
        default_factory=dict
    )
    enabled: Callable[[Any], bool] = field(
        default=lambda _config: True
    )


class SocialTriggerRegistry:
    """SocialTrigger注册表

    集中管理所有主动社交触发器的注册与查询，
    替代原先的模块级散装函数。setup_to_scheduler将
    所有已注册触发器按schedule_kind注册到APScheduler。
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

    def list(self) -> list[SocialTrigger]:
        """列出所有已注册的触发器

        返回:
            list[SocialTrigger]: 触发器列表
        """
        return list(self._registry.values())

    async def setup_to_scheduler(self) -> int:
        """将所有触发器注册到APScheduler调度

        遍历注册表，跳过event类型与disabled的触发器，
        按schedule_kind调用task_manager.add_cron_task /
        add_interval_task。event类型由消息钩子手动触发，
        不在此注册。

        返回:
            int: 成功注册的触发器数量
        """
        count = 0
        for trigger in self.list():
            if not trigger.enabled(None):
                continue
            if trigger.schedule_kind == "event":
                continue
            wrapped = self._wrap_handler(trigger.handler)
            task_id = f"ai_social_{trigger.name}"
            try:
                if trigger.schedule_kind == "cron":
                    await task_manager.add_cron_task(
                        task_id=task_id,
                        func=wrapped,
                        **trigger.schedule_args,
                    )
                elif trigger.schedule_kind == "interval":
                    await task_manager.add_interval_task(
                        task_id=task_id,
                        func=wrapped,
                        **trigger.schedule_args,
                    )
                else:
                    logger.debug(
                        f"未知调度类型 {trigger.schedule_kind}，"
                        f"跳过触发器 {trigger.name}",
                        command="AI",
                    )
                    continue
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
        handler: Callable[[SocialContext], Awaitable[None]],
    ) -> Callable[[], Awaitable[None]]:
        """包装handler为无参数协程

        SocialTrigger.handler接收SocialContext，但APScheduler
        的任务函数无参数。包装时传入空SocialContext，
        handler内部自行遍历目标群/用户。

        参数:
            handler: 触发器处理函数

        返回:
            无参数协程函数
        """

        async def _wrapped() -> None:
            await handler(SocialContext())

        return _wrapped


social_trigger_registry = SocialTriggerRegistry()
