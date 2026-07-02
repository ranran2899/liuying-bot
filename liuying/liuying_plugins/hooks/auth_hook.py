from nonebot.adapters import Bot, Event
from nonebot.matcher import Matcher
from nonebot.message import run_postprocessor, run_preprocessor
from nonebot_plugin_alconna import UniMsg
from nonebot_plugin_uninfo import Uninfo

from .auth.utils import get_group_channel_ids
from .auth_checker import LimitManager, auth


@run_preprocessor
async def _(
    matcher: Matcher, event: Event, bot: Bot, session: Uninfo, message: UniMsg
):
    """权限检测"""
    await auth(matcher, event, bot, session, message)


@run_postprocessor
async def _(
    matcher: Matcher,
    exception: Exception | None,
    bot: Bot,
    event: Event,
    session: Uninfo,
):
    """解除命令block阻塞"""
    user_id = session.user.id
    ids = get_group_channel_ids(session)
    if user_id and matcher.plugin:
        LimitManager.unblock(matcher.plugin.name, user_id, ids.group_id, ids.channel_id)
