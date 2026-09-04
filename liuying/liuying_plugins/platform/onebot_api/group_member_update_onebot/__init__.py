from nonebot import on_notice
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import GroupIncreaseNoticeEvent
from nonebot.adapters.onebot.v12 import GroupMemberIncreaseEvent
from nonebot.plugin import PluginMetadata

from liuying.configs.config import BotConfig
from liuying.configs.utils import PluginExtraData
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.rules import notice_rule

from .data_source import MemberUpdateManage

__plugin_meta__ = PluginMetadata(
    name="QQ群成员信息更新",
    description="OneBot平台群成员信息更新，Bot进群时自动更新群组成员列表",
    usage="",
    extra=PluginExtraData(
        author="liuying",
        version="0.1",
        plugin_type=PluginType.HIDDEN,
    ).to_dict(),
)


_notice = on_notice(
    priority=1,
    block=False,
    rule=notice_rule([GroupIncreaseNoticeEvent, GroupMemberIncreaseEvent]),
)


@_notice.handle()
async def _(bot: Bot, event: GroupIncreaseNoticeEvent | GroupMemberIncreaseEvent):
    if str(event.user_id) == bot.self_id:
        await MemberUpdateManage.update_group_member(bot, str(event.group_id))
        logger.info(
            f"{BotConfig.self_nickname}加入群聊更新群组信息",
            "更新群组成员列表",
            session=event.user_id,
            group_id=event.group_id,
        )
