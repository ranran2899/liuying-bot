"""QQ官方适配器群事件数据处理

群事件的业务逻辑封装,与OneBot qq插件GroupManager的职责对齐:
- 机器人进退群 -> GroupConsole增删 + GroupConfig配置初始化
- 成员进退 -> GroupInfoUser增删 + EventLog
- 成员退群 -> 发送退群提醒(受被动技能 qq_refund_group_remind 控制)
"""

from datetime import datetime

from nonebot.adapters.qq import Bot

from liuying.models._group import GroupConfig, GroupConsole, GroupInfoUser
from liuying.models._log.event_log import EventLog
from liuying.utils.common_utils import CommonUtils
from liuying.utils.enum import EventLogType
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils


class GroupManager:
    """QQ官方群事件业务处理"""

    @classmethod
    async def add_bot(cls, group_openid: str, operator_openid: str) -> None:
        """处理机器人进群

        参数:
            group_openid: 群openid
            operator_openid: 操作者openid
        """
        logger.info("机器人被添加到群", "QQ官方事件", target=group_openid)
        await GroupConsole.update_or_create(
            group_id=group_openid,
            channel_id=None,
            defaults={
                "platform": "qq",
                "group_flag": 1,
                "status": True,
            },
        )
        await GroupConfig.get_or_create_config(group_openid)
        await EventLog.create(
            user_id=operator_openid,
            group_id=group_openid,
            event_type=EventLogType.GROUP_MEMBER_INCREASE,
        )

    @classmethod
    async def del_bot(cls, group_openid: str, operator_openid: str) -> None:
        """处理机器人退群或被踢

        参数:
            group_openid: 群openid
            operator_openid: 操作者openid
        """
        logger.info("机器人被移出群", "QQ官方事件", target=group_openid)
        group = await GroupConsole.filter(group_id=group_openid).first()
        if group:
            await group.delete()
        await EventLog.create(
            user_id=operator_openid,
            group_id=group_openid,
            event_type=EventLogType.KICK_BOT,
        )

    @classmethod
    async def set_proactive_status(cls, group_openid: str, allowed: bool) -> None:
        """更新群聊主动消息状态

        参数:
            group_openid: 群openid
            allowed: 是否允许主动消息
        """
        await GroupConfig.set_proactive_status(group_openid, allowed)

    @classmethod
    async def add_user(cls, group_openid: str, member_openid: str) -> None:
        """处理成员进群

        参数:
            group_openid: 群openid
            member_openid: 成员openid
        """
        logger.info("新成员加入群聊", "QQ官方事件", target=member_openid)
        await GroupInfoUser.update_or_create(
            user_id=member_openid,
            group_id=group_openid,
            defaults={
                "platform": "qq",
                "user_join_time": datetime.now(),
            },
        )
        await EventLog.create(
            user_id=member_openid,
            group_id=group_openid,
            event_type=EventLogType.GROUP_MEMBER_INCREASE,
        )

    @classmethod
    async def run_user(cls, bot: Bot, group_openid: str, member_openid: str) -> None:
        """处理成员退群并发送退群提醒

        参数:
            bot: Bot实例
            group_openid: 群openid
            member_openid: 成员openid
        """
        logger.info("成员退出群聊", "QQ官方事件", target=member_openid)
        user_name = member_openid[-6:]
        if user := await GroupInfoUser.filter(
            user_id=member_openid, group_id=group_openid
        ).first():
            user_name = user.user_name or user_name
            await user.delete()
        await EventLog.create(
            user_id=member_openid,
            group_id=group_openid,
            event_type=EventLogType.GROUP_MEMBER_DECREASE,
        )
        if await CommonUtils.task_is_block(
            bot, "qq_refund_group_remind", group_id=group_openid
        ):
            return
        message = await MessageUtils.build_message(
            f"{user_name} 永远的离开了我们..."
        ).export(bot)
        try:
            await bot.send_to_group(group_openid, message)
            logger.info(
                "发送退群提醒成功",
                "QQ官方事件",
                target=group_openid,
            )
        except Exception as e:
            logger.error(
                "发送退群提醒失败",
                "QQ官方事件",
                target=group_openid,
                e=e,
            )
