"""QQ官方适配器群成员信息更新插件

机器人被拉入群聊(GroupAddRobotEvent)时自动调用QQ开放平台
/v2/groups/{group_openid}/members 接口拉取并更新群成员列表
"""

from nonebot import on_notice
from nonebot.adapters import Event
from nonebot.adapters.qq import Bot, GroupAddRobotEvent
from nonebot.adapters.qq import Event as QQEvent
from nonebot.plugin import PluginMetadata

from liuying.configs.utils import PluginExtraData
from liuying.utils.enum import PluginType
from liuying.utils.log import logger

from .data_source import MemberUpdateManage

__plugin_meta__ = PluginMetadata(
    name="QQ官方群成员信息更新",
    description="QQ官方适配器群成员信息更新，机器人进群时自动拉取群成员列表",
    usage="",
    extra=PluginExtraData(
        author="liuying",
        version="0.1",
        plugin_type=PluginType.HIDDEN,
    ).to_dict(),
)


def _qbot_rule(event: Event) -> bool:
    """QQ官方适配器事件过滤规则

    参数:
        event: 事件对象

    返回:
        bool: 是否为QQ官方适配器事件
    """
    return isinstance(event, QQEvent)


_group_add_robot = on_notice(priority=1, block=False, rule=_qbot_rule)


@_group_add_robot.handle()
async def _(bot: Bot, event: Event):
    if isinstance(event, GroupAddRobotEvent):
        result = await MemberUpdateManage.update_group_member(
            bot, event.group_openid
        )
        logger.info(
            "机器人进群更新群成员信息",
            "QQ官方群成员信息更新",
            target=event.group_openid,
            result=result,
        )
