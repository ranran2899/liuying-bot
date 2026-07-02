import nonebot
from nonebot import on_notice
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import GroupIncreaseNoticeEvent
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Arparma, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.config import BotConfig
from liuying.configs.utils import PluginExtraData
from liuying.utils.apscheduler import task_manager
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils
from liuying.utils.platform import PlatformUtils
from liuying.utils.rules import admin_check, ensure_group, notice_rule

from ._data_source import MemberUpdateManage

__plugin_meta__ = PluginMetadata(
    name="更新群组成员列表",
    description="更新群组成员列表",
    usage="""
    更新群组成员的基本信息
    指令：
        更新群组成员信息
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.1",
        plugin_type=PluginType.SUPER_AND_ADMIN,
        admin_level=1,
    ).to_dict(),
)


_matcher = on_alconna(
    Alconna("更新群组成员信息"),
    rule=admin_check(1) & ensure_group,
    priority=5,
    block=True,
)


_notice = on_notice(priority=1, block=False, rule=notice_rule(GroupIncreaseNoticeEvent))


@_matcher.handle()
async def _(bot: Bot, session: Uninfo, arparma: Arparma):
    if gid := session.group.id if session.group else None:
        logger.info("更新群组成员信息", arparma.header_result, session=session)
        result = await MemberUpdateManage.update_group_member(bot, gid)
        await MessageUtils.build_message(result).finish(reply_to=True)
    await MessageUtils.build_message("群组id为空...").send()


@_notice.handle()
async def _(bot: Bot, event: GroupIncreaseNoticeEvent):
    if str(event.user_id) == bot.self_id:
        await MemberUpdateManage.update_group_member(bot, str(event.group_id))
        logger.info(
            f"{BotConfig.self_nickname}加入群聊更新群组信息",
            "更新群组成员列表",
            session=event.user_id,
            group_id=event.group_id,
        )


@task_manager.interval_task("update_group_member", minutes=5)
async def _update_group_member():
    """每5分钟更新一次群组成员信息"""
    for bot in list(nonebot.get_bots().values()):
        if PlatformUtils.get_platform(bot) == "qq":
            try:
                group_list, _ = await PlatformUtils.get_group_list(bot)
                if group_list:
                    for group in group_list:
                        try:
                            await MemberUpdateManage.update_group_member(
                                bot, group.group_id
                            )
                            logger.debug("自动更新群组成员信息成功...")
                        except Exception as e:
                            logger.error(
                                f"Bot: {bot.self_id} 自动更新群组成员信息失败",
                                target=group.group_id,
                                e=e,
                            )
            except Exception as e:
                logger.error(f"Bot: {bot.self_id} 自动更新群组成员信息失败", e=e)
            else:
                logger.debug(f"自动 Bot: {bot.self_id} 更新群组成员信息成功...")
