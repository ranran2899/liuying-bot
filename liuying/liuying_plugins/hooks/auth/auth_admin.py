import time

from nonebot_plugin_alconna import At
from nonebot_plugin_uninfo import Uninfo

from liuying.models._user import UserLevel
from liuying.models.plugin_info import PluginInfo
from liuying.utils.log import logger

from .config import LOGGER_COMMAND, WARNING_THRESHOLD
from .exception import SkipPluginException
from .utils import get_group_channel_ids, send_message


async def auth_admin(plugin: PluginInfo, session: Uninfo):
    """管理员命令 个人权限

    参数:
        plugin: PluginInfo
        session: Uninfo
    """
    start_time = time.time()

    if not plugin.admin_level:
        return

    try:
        user_id = session.user.id
        ids = get_group_channel_ids(session)

        bot_id = session.self_id if hasattr(session, "self_id") else None

        user_level = await UserLevel.get_level(
            user_id, bot_id, ids.group_id
        )

        if user_level < plugin.admin_level:
            await send_message(
                session,
                [
                    At(flag="user", target=user_id),
                    f"你的权限不足喔，该功能需要的权限等级: {plugin.admin_level}",
                ],
                user_id,
            )
            raise SkipPluginException(
                f"{plugin.name}({plugin.module}) 管理员权限不足..."
            )
    finally:
        elapsed = time.time() - start_time
        if elapsed > WARNING_THRESHOLD:
            logger.warning(
                f"auth_admin 耗时: {elapsed:.3f}s, plugin={plugin.module}",
                LOGGER_COMMAND,
                session=session,
            )
