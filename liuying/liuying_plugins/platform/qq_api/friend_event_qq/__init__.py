"""QQ官方适配器好友事件处理

监听QQ官方适配器的好友事件:
- FriendAddEvent/FriendDelEvent: 好友增减

适配器类型区分:
- QQ官方适配器(nonebot.adapters.qq): 使用OpenID
- OneBot适配器(nonebot.adapters.onebot): 使用QQ号
本插件仅处理QQ官方适配器事件,OneBot事件由qq插件处理
"""

from nonebot import on_notice
from nonebot.adapters import Event
from nonebot.adapters.qq import Bot, FriendAddEvent, FriendDelEvent
from nonebot.adapters.qq import Event
from nonebot.plugin import PluginMetadata

from liuying.configs.utils import PluginExtraData
from liuying.models._bot import BotFriend
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.rules import notice_rule

__plugin_meta__ = PluginMetadata(
    name="QQ官方好友事件监听",
    description="QQ官方适配器好友增减事件处理",
    usage="",
    extra=PluginExtraData(
        author="liuying",
        version="0.1",
        plugin_type=PluginType.HIDDEN,
    ).to_dict(),
)


# 好友增减事件
_friend_event = on_notice(
    priority=1,
    block=False,
    rule=notice_rule([FriendAddEvent, FriendDelEvent]))


@_friend_event.handle()
async def _handle_friend_event(event: Event, bot: Bot) -> None:
    """处理好友添加/删除事件

    QQ官方适配器: FriendAddEvent/FriendDelEvent -> BotFriend增删
    """
    if isinstance(event, FriendAddEvent):
        open_id = event.openid
        logger.info("新好友添加", "QQ官方事件", target=open_id)
        await BotFriend.update_or_create(
            bot_id=bot.self_id,
            user_id=open_id,
            defaults={"platform": "QQ"},
        )
    elif isinstance(event, FriendDelEvent):
        open_id = event.openid
        logger.info("好友删除", "QQ官方事件", target=open_id)
        await BotFriend.delete_friend(bot.self_id, open_id)
