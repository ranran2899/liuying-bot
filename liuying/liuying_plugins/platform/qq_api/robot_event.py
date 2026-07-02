"""QQ官方适配器机器人事件处理

监听QQ官方适配器的群机器人事件和好友事件:
- GroupAddRobotEvent: 机器人被添加到群
- GroupDelRobotEvent: 机器人被移出群
- GroupMsgRejectEvent: 群聊拒绝机器人主动消息
- GroupMsgReceiveEvent: 群聊允许接收机器人主动消息
- FriendAddEvent: 好友添加
- FriendDelEvent: 好友删除

注意: QQ官方适配器不支持普通群成员进退事件(仅频道Guild支持)

适配器类型区分:
- QQ官方适配器(nonebot.adapters.qq): 使用GroupOpenID,不支持群成员列表
- OneBot适配器(nonebot.adapters.onebot): 使用群号,支持完整群管理
本文件仅处理QQ官方适配器事件,OneBot事件由qq插件处理
"""

from nonebot import on_notice
from nonebot.adapters import Event
from nonebot.adapters.qq import Event as QQEvent
from nonebot.adapters.qq import (
    FriendAddEvent,
    FriendDelEvent,
    GroupAddRobotEvent,
    GroupDelRobotEvent,
    GroupMsgReceiveEvent,
    GroupMsgRejectEvent,
)
from nonebot.plugin import PluginMetadata

from liuying.configs.utils import PluginExtraData
from liuying.models._bot import BotFriend
from liuying.models._log.event_log import EventLog
from liuying.models._group import GroupConsole
from liuying.utils.enum import EventLogType, PluginType
from liuying.utils.log import logger

__plugin_meta__ = PluginMetadata(
    name="QQ官方机器人事件监听",
    description="QQ官方适配器机器人进退群、主动消息状态、好友增减事件处理",
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


# 机器人进退群事件
_group_robot_event = on_notice(priority=1, block=False, rule=_qbot_rule)


@_group_robot_event.handle()
async def _handle_group_robot_event(event: Event, bot) -> None:
    """处理机器人进退群事件

    QQ官方适配器: GroupAddRobotEvent/GroupDelRobotEvent -> GroupConsole增删 + EventLog
    与OneBot qq插件的差异: 无法获取群名/人数,无法刷新管理员权限
    """
    if isinstance(event, GroupAddRobotEvent):
        group_openid = event.group_openid
        operator_openid = event.op_member_openid
        logger.info("机器人被添加到群", "QQ官方事件", target=group_openid)
        await GroupConsole.update_or_create(
            group_id=group_openid,
            channel_id=None,
            defaults={
                "platform": "qq",
                "group_flag": 1,
                "status": True,
                "proactive_allowed": True,
            },
        )
        await EventLog.create(
            user_id=operator_openid,
            group_id=group_openid,
            event_type=EventLogType.GROUP_MEMBER_INCREASE,
        )
    elif isinstance(event, GroupDelRobotEvent):
        group_openid = event.group_openid
        operator_openid = event.op_member_openid
        logger.info("机器人被移出群", "QQ官方事件", target=group_openid)
        group = await GroupConsole.filter(group_id=group_openid).first()
        if group:
            await group.delete()
        await EventLog.create(
            user_id=operator_openid,
            group_id=group_openid,
            event_type=EventLogType.KICK_BOT,
        )


# 群聊主动消息状态变更事件
_group_msg_status = on_notice(priority=1, block=False, rule=_qbot_rule)


@_group_msg_status.handle()
async def _handle_group_msg_status(event: Event, bot) -> None:
    """处理群聊主动消息开关变更事件

    用户在群内关闭/重新打开主动消息开关,更新GroupConsole.proactive_allowed
    参考QQ官方文档: 群聊拒绝/允许接收机器人主动消息
    """
    if isinstance(event, GroupMsgRejectEvent):
        group_openid = event.group_openid
        logger.info(
            "群聊拒绝机器人主动消息",
            "QQ官方事件",
            target=group_openid,
        )
        await GroupConsole.set_proactive_status(group_openid, allowed=False)
    elif isinstance(event, GroupMsgReceiveEvent):
        group_openid = event.group_openid
        logger.info(
            "群聊允许接收机器人主动消息",
            "QQ官方事件",
            target=group_openid,
        )
        await GroupConsole.set_proactive_status(group_openid, allowed=True)


# 好友增减事件
_friend_event = on_notice(priority=1, block=False, rule=_qbot_rule)


@_friend_event.handle()
async def _handle_friend_event(event: Event, bot) -> None:
    """处理好友添加/删除事件

    QQ官方适配器: FriendAddEvent/FriendDelEvent -> BotFriend增删
    """
    if isinstance(event, FriendAddEvent):
        open_id = event.openid
        logger.info("新好友添加", "QQ官方事件", target=open_id)
        await BotFriend.update_or_create(
            bot_id=bot.self_id,
            user_id=open_id,
            defaults={"platform": "qq"},
        )
    elif isinstance(event, FriendDelEvent):
        open_id = event.openid
        logger.info("好友删除", "QQ官方事件", target=open_id)
        await BotFriend.delete_friend(bot.self_id, open_id)
