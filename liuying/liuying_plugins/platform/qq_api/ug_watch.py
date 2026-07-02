from nonebot import on_message
from nonebot.plugin import PluginMetadata
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import PluginExtraData
from liuying.models._bot import BotFriend
from liuying.models._group import GroupConsole
from liuying.models._group import GroupInfoUser
from liuying.services.log import logger
from liuying.utils.enum import PluginType
from liuying.utils.platform import PlatformUtils

__plugin_meta__ = PluginMetadata(
    name="QQ官方用户群组监听",
    description="QQ官方适配器用户和群组信息自动记录",
    usage="",
    extra=PluginExtraData(
        author="liuying",
        version="0.1",
        plugin_type=PluginType.HIDDEN,
    ).to_dict(),
)


def rule(session: Uninfo) -> bool:
    return PlatformUtils.is_qbot(session)


_matcher = on_message(priority=5, block=False, rule=rule)


@_matcher.handle()
async def _(session: Uninfo):
    if session.group:
        if not await GroupConsole.filter(group_id=session.group.id).exists():
            await GroupConsole.create(group_id=session.group.id)
            logger.info("添加当前群组ID信息", session=session)
        await GroupInfoUser.update_or_create(
            user_id=session.user.id,
            group_id=session.group.id,
            platform=PlatformUtils.get_platform(session),
        )
    elif not await BotFriend.filter(
        bot_id=session.self_id, user_id=session.user.id
    ).exists():
        await BotFriend.create(
            bot_id=session.self_id,
            user_id=session.user.id,
            platform=PlatformUtils.get_platform(session),
        )
        logger.info("添加当前好友用户信息", "", session=session)
