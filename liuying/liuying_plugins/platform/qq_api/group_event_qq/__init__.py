"""QQ官方适配器群组事件处理

监听QQ官方适配器的群事件:
- GroupAddRobotEvent/GroupDelRobotEvent: 机器人进退群
- GroupMsgRejectEvent/GroupMsgReceiveEvent: 群聊主动消息状态
- GroupMemberAddEvent/GroupMemberRemoveEvent: 普通群成员进退(含退群提醒)

注意: 普通群成员进退事件需要在适配器 intent 配置中开启 group_members=true,
     同时需在QQ开放平台后台申请群成员事件权限;
     退群提醒为主动消息,受群主动消息开关和消息频率限制

适配器类型区分:
- QQ官方适配器(nonebot.adapters.qq): 使用GroupOpenID,不支持群成员列表
- OneBot适配器(nonebot.adapters.onebot): 使用群号,支持完整群管理
本插件仅处理QQ官方适配器事件,OneBot事件由qq插件处理
"""

from nonebot import on_notice
from nonebot.adapters import Event
from nonebot.adapters.qq import (
    Bot,
    GroupAddRobotEvent,
    GroupDelRobotEvent,
    GroupMemberAddEvent,
    GroupMemberRemoveEvent,
    GroupMsgReceiveEvent,
    GroupMsgRejectEvent,
)
from nonebot.adapters.qq import Event
from nonebot.plugin import PluginMetadata

from liuying.configs.utils import PluginExtraData, Task
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.rules import notice_rule

from .data_source import GroupManager

__plugin_meta__ = PluginMetadata(
    name="QQ官方群事件监听",
    description="QQ官方适配器机器人进退群、群成员进退、主动消息状态事件处理",
    usage="",
    extra=PluginExtraData(
        author="liuying",
        version="0.2",
        plugin_type=PluginType.HIDDEN,
        tasks=[
            Task(
                module="qq_refund_group_remind",
                name="退群提醒(QQ官方)",
                create_status=False,
                default_status=False,
            ),
        ],
    ).to_dict(),
)



# 机器人进退群事件
_group_robot_event = on_notice(priority=1, block=False, rule=notice_rule([GroupAddRobotEvent, GroupDelRobotEvent]))


@_group_robot_event.handle()
async def _handle_group_robot_event(event: Event) -> None:
    """处理机器人进退群事件

    与OneBot qq插件的差异: 无法获取群名/人数,无法刷新管理员权限
    """
    if isinstance(event, GroupAddRobotEvent):
        await GroupManager.add_bot(event.group_openid, event.op_member_openid)
    elif isinstance(event, GroupDelRobotEvent):
        await GroupManager.del_bot(event.group_openid, event.op_member_openid)


# 群聊主动消息状态变更事件
_group_msg_status = on_notice(priority=1, block=False, rule=notice_rule([GroupMsgRejectEvent, GroupMsgReceiveEvent]))


@_group_msg_status.handle()
async def _handle_group_msg_status(event: Event) -> None:
    """处理群聊主动消息开关变更事件

    用户在群内关闭/重新打开主动消息开关,更新GroupConfig.proactive_allowed
    参考QQ官方文档: 群聊拒绝/允许接收机器人主动消息
    """
    if isinstance(event, GroupMsgRejectEvent):
        logger.info(
            "群聊拒绝机器人主动消息",
            "QQ官方事件",
            target=event.group_openid,
        )
        await GroupManager.set_proactive_status(event.group_openid, allowed=False)
    elif isinstance(event, GroupMsgReceiveEvent):
        logger.info(
            "群聊允许接收机器人主动消息",
            "QQ官方事件",
            target=event.group_openid,
        )
        await GroupManager.set_proactive_status(event.group_openid, allowed=True)


# 普通群成员进退事件
_group_member_event = on_notice(priority=1, block=False, rule=notice_rule([GroupMemberAddEvent, GroupMemberRemoveEvent]))


@_group_member_event.handle()
async def _handle_group_member_event(event: Event, bot: Bot) -> None:
    """处理普通群成员进退事件

    与OneBot qq插件的差异: 仅提供成员openid,无法获取昵称,无法区分主动退出与被踢
    """
    if isinstance(event, GroupMemberAddEvent):
        await GroupManager.add_user(event.group_openid, event.member_openid)
    elif isinstance(event, GroupMemberRemoveEvent):
        await GroupManager.run_user(bot, event.group_openid, event.member_openid)
