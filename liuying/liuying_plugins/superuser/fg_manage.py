from nonebot.adapters import Bot
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot_plugin_alconna import Alconna, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import PluginExtraData
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

__plugin_meta__ = PluginMetadata(
    name="好友群组列表",
    description="查看好友群组列表",
    usage="""
        查看所有好友
        查看所有群组
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.1",
        plugin_type=PluginType.SUPERUSER,
    ).to_dict(),
)

_friend_matcher = on_alconna(
    Alconna("好友列表"),
    rule=to_me(),
    permission=SUPERUSER,
    priority=1,
    block=True,
)

_group_matcher = on_alconna(
    Alconna("群组列表"),
    rule=to_me(),
    permission=SUPERUSER,
    priority=1,
    block=True,
)


@_friend_matcher.handle()
async def _(
    bot: Bot,
    session: Uninfo,
):
    try:
        fl = await bot.get_friend_list()
        msg = ["{user_id} {nickname}".format_map(g) for g in fl]
        msg = "\n".join(msg)
        msg = f"| UID | 昵称 | 共{len(fl)}个好友\n" + msg
        await MessageUtils.build_message(msg).send()
        logger.info("查看好友列表", "好友列表", session=session)
    except Exception as e:
        logger.error("好友列表发生错误", "好友列表", session=session, e=e)
        await MessageUtils.build_message("其他未知错误...").send()


@_group_matcher.handle()
async def _(
    bot: Bot,
    session: Uninfo,
):
    try:
        gl = await bot.get_group_list()
        msg = ["{group_id} {group_name}".format_map(g) for g in gl]
        msg = "\n".join(msg)
        msg = f"| GID | 名称 | 共{len(gl)}个群组\n" + msg
        await MessageUtils.build_message(msg).send()
        logger.info("查看群组列表", "群组列表", session=session)
    except Exception as e:
        logger.error("查看群组列表发生错误", "群组列表", session=session, e=e)
        await MessageUtils.build_message("其他未知错误...").send()
