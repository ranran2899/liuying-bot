from nonebot.adapters import Bot, Event
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule
from nonebot_plugin_alconna import Alconna, Arparma, on_alconna
from nonebot_plugin_alconna.uniseg.tools import reply_fetch
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import Command, PluginExtraData
from liuying.utils.log import logger
from liuying.utils.manager.message_manager import MessageManager
from liuying.utils.message import MessageUtils
from liuying.utils.platform import PlatformUtils

__plugin_meta__ = PluginMetadata(
    name="消息撤回",
    description="撤回bot自己触发的消息撤回",
    usage="""
    引用消息 撤回
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.1",
        menu_type="其他",
        commands=[Command(command="[引用消息] 撤回")],
    ).to_dict(),
)


def reply_check() -> Rule:
    """
    检查是否存在回复消息

    返回:
        Rule: Rule
    """

    async def _rule(bot: Bot, event: Event, session: Uninfo):
        if event.get_type() == "message":
            return (
                bool(await reply_fetch(event, bot))
                and PlatformUtils.get_platform(session) == "qq"
            )
        return False

    return Rule(_rule)


_matcher = on_alconna(Alconna("撤回"), priority=5, block=True, rule=reply_check())


@_matcher.handle()
async def _(bot: Bot, event: Event, session: Uninfo, arparma: Arparma):
    if reply := await reply_fetch(event, bot):
        can_withdraw = (
            session.user.id in bot.config.superusers
            or MessageManager.check(session.user.id, reply.id)
        )
        if can_withdraw:
            try:
                await bot.delete_msg(message_id=reply.id)
                logger.info("撤回消息", arparma.header_result, session=session)
            except Exception:
                await MessageUtils.build_message("撤回失败，可能消息已过期...").send()
        else:
            await MessageUtils.build_message(
                "权限不足，不是你触发的消息不要胡乱撤回哦..."
            ).send()
