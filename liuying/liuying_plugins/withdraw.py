from nonebot.adapters import Bot, Event
from nonebot.adapters.qq import Bot as qqBot
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule
from nonebot_plugin_alconna import Alconna, Arparma, on_alconna
from nonebot_plugin_alconna.uniseg.tools import reply_fetch
from nonebot_plugin_uninfo import SceneType, Uninfo

from liuying.configs.utils import Command, PluginExtraData
from liuying.utils.log import logger
from liuying.utils.manager.message_manager import MessageManager
from liuying.utils.manager.withdraw_manager import WithdrawManager
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


async def _withdraw_qq_message(bot: qqBot, session: Uninfo, arparma: Arparma):
    """QQ官方适配器撤回

    官方事件中被引用消息不携带消息ID，撤回bot在当前会话最近发送的一条消息。

    参数:
        bot: QQ官方适配器机器人实例
        session: 会话信息
        arparma: 命令解析结果
    """
    record = MessageManager.pop_last(session.scene.id)
    if record is None:
        if session.user.id in bot.config.superusers:
            await MessageUtils.build_message("撤回失败，可能消息已过期...").send()
        else:
            await MessageUtils.build_message(
                "权限不足，不是你触发的消息不要胡乱撤回哦..."
            ).send()
        return
    msg_id, openid = record
    try:
        await WithdrawManager.withdraw_message(
            bot,
            msg_id,
            openid=openid,
            is_group=session.scene.type == SceneType.GROUP,
        )
        logger.info("撤回消息", arparma.header_result, session=session)
    except Exception:
        await MessageUtils.build_message("撤回失败，可能消息已过期...").send()


@_matcher.handle()
async def _(bot: Bot, event: Event, session: Uninfo, arparma: Arparma):
    if isinstance(bot, qqBot):
        await _withdraw_qq_message(bot, session, arparma)
        return
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
