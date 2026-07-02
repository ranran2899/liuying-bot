from nonebot.adapters import Bot, Event
from nonebot.exception import IgnoredException
from nonebot.matcher import Matcher
from nonebot.message import run_preprocessor
from nonebot.typing import T_State
from nonebot_plugin_uninfo import Uninfo

from liuying.models._group import GroupConsole
from liuying.utils.enum import PluginType
from liuying.utils.log import logger

from .auth.utils import get_group_channel_ids


@run_preprocessor
async def _(
    matcher: Matcher, bot: Bot, event: Event, state: T_State, session: Uninfo
):
    """检查群组黑名单等级

    注意: 用户/群组 ban 检查已由 auth_ban 统一处理，
    此处仅检查 GroupConsole.level < 0 的群组黑名单等级
    """
    if plugin := matcher.plugin:
        if metadata := plugin.metadata:
            extra = metadata.extra
            if extra and extra.get("plugin_type") in {
                PluginType.HIDDEN,
                PluginType.DEPENDANT,
            }:
                return

    user_id = session.user.id
    if user_id in bot.config.superusers:
        return

    ids = get_group_channel_ids(session)

    if ids.group_id:
        if g := await GroupConsole.get_group(ids.group_id):
            if g.level < 0:
                logger.debug("群黑名单, 群权限-1...", "ban_hook")
                raise IgnoredException("群黑名单, 群权限-1..")
