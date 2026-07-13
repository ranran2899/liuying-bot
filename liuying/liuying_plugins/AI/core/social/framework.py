"""SocialTrigger框架

把"什么时候触发"（cron/interval/event）与"触发后做什么"
（handler）解耦。handler通过SocialContext拿到运行所需的
全部依赖，便于测试和扩展。

注册表模式：register_social_trigger注册触发器，
list_social_triggers列出所有已注册的触发器。
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "SocialContext",
    "SocialTrigger",
    "list_social_triggers",
    "register_social_trigger",
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
        name: 触发器名称
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


_REGISTRY: dict[str, SocialTrigger] = {}


def register_social_trigger(
    trigger: SocialTrigger,
) -> None:
    """注册一个SocialTrigger

    重名会覆盖（便于热重载）。

    参数:
        trigger: 触发器配置
    """
    _REGISTRY[trigger.name] = trigger


def list_social_triggers() -> list[SocialTrigger]:
    """列出所有已注册的触发器

    返回:
        list[SocialTrigger]: 触发器列表
    """
    return list(_REGISTRY.values())
