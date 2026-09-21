"""统一动作执行器基类

参照 fetch.py 的 InfoFetcher 模式，将各适配器差异较大的管理类写操作
(撤回、禁言、解禁、踢出等) 抽象为统一接口，
入参统一使用 Scene/Member 模型，屏蔽平台细节。

消息发送与回复统一交由 nonebot_plugin_alconna 的 UniMessage 处理，
本模块不再重复实现。

能力探测通过检测子类是否重写对应方法来自动推导，
避免手工维护支持清单与实际实现漂移。
"""

from abc import ABC
from datetime import timedelta
from enum import StrEnum
from typing import Any

from nonebot.adapters import Bot

from .model import Member, Scene, Session


class Action(StrEnum):
    """统一动作类型"""

    RECALL = "recall"
    """撤回消息"""
    MUTE = "mute"
    """禁言成员"""
    UNMUTE = "unmute"
    """取消禁言"""
    KICK = "kick"
    """踢出成员"""


def resolve_scene(target: Scene | Session) -> Scene:
    """从会话或场景中解析出目标场景"""
    return target.scene if isinstance(target, Session) else target


class ActionNotSupported(Exception):
    """适配器不支持指定动作时抛出"""

    def __init__(self, adapter: Any, action: Action) -> None:
        self.adapter = adapter
        self.action = action
        super().__init__(f"适配器 {adapter} 不支持 {action.value} 动作")


class ActionExecutor(ABC):
    """统一动作执行器，由各适配器子类实现具体调用逻辑

    未实现的动作会抛出 NotImplementedError，
    capabilities() 依据子类重写情况自动推导受支持的动作集合。
    """

    def __init__(self, adapter: Any) -> None:
        self.adapter = adapter

    @classmethod
    def capabilities(cls) -> frozenset[Action]:
        """推导当前执行器受支持的动作集合

        返回:
            frozenset[Action]: 已被子类重写实现的动作
        """
        base = ActionExecutor
        caps: set[Action] = set()
        if cls.recall is not base.recall:
            caps.add(Action.RECALL)
        if cls.mute is not base.mute:
            caps.add(Action.MUTE)
        if cls.unmute is not base.unmute:
            caps.add(Action.UNMUTE)
        if cls.kick is not base.kick:
            caps.add(Action.KICK)
        return frozenset(caps)

    def supports(self, action: Action | str) -> bool:
        """判断是否支持指定动作

        参数:
            action: 动作类型或其字符串值
        """
        try:
            target = Action(action)
        except ValueError:
            return False
        return target in self.capabilities()

    async def recall(
        self, bot: Bot, target: Scene | Session, message_id: str
    ) -> bool:
        """撤回指定会话或场景中的消息

        参数:
            bot: 发起动作的机器人实例
            target: 消息所在的目标场景或完整会话
            message_id: 待撤回的消息id

        返回:
            bool: 撤回是否成功

        异常:
            NotImplementedError: 当前适配器不支持撤回时抛出
        """
        raise NotImplementedError

    async def mute(
        self, bot: Bot, member: Member, scene: Scene, duration: timedelta
    ) -> bool:
        """禁言指定场景中的成员

        参数:
            bot: 发起动作的机器人实例
            member: 待禁言的目标成员
            scene: 成员所属的场景
            duration: 禁言时长

        返回:
            bool: 禁言是否成功

        异常:
            NotImplementedError: 当前适配器不支持禁言时抛出
        """
        raise NotImplementedError

    async def unmute(self, bot: Bot, member: Member, scene: Scene) -> bool:
        """取消指定场景中成员的禁言

        参数:
            bot: 发起动作的机器人实例
            member: 待解禁的目标成员
            scene: 成员所属的场景

        返回:
            bool: 解禁是否成功

        异常:
            NotImplementedError: 当前适配器不支持解禁时抛出
        """
        raise NotImplementedError

    async def kick(self, bot: Bot, member: Member, scene: Scene) -> bool:
        """将指定成员移出场景

        参数:
            bot: 发起动作的机器人实例
            member: 待移出的目标成员
            scene: 成员所属的场景

        返回:
            bool: 移出是否成功

        异常:
            NotImplementedError: 当前适配器不支持踢出时抛出
        """
        raise NotImplementedError
