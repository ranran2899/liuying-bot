import time

from nonebot_plugin_uninfo import Uninfo

from liuying.models._user.user_info import UserInfo
from liuying.models.plugin_info import PluginInfo
from liuying.utils.log import logger

from .config import LOGGER_COMMAND, WARNING_THRESHOLD
from .exception import SkipPluginException
from .utils import send_message


async def auth_cost(user: UserInfo, plugin: PluginInfo, session: Uninfo) -> int:
    """检测是否满足金币条件

    参数:
        user: UserInfo
        plugin: PluginInfo
        session: Uninfo

    返回:
        int: 需要消耗的金币
    """
    start_time = time.time()

    try:
        if user.gold < plugin.cost_gold:
            await send_message(
                session, f"金币不足..该功能需要{plugin.cost_gold}金币.."
            )
            raise SkipPluginException(f"{plugin.name}({plugin.module}) 金币限制...")
        return plugin.cost_gold
    finally:
        elapsed = time.time() - start_time
        if elapsed > WARNING_THRESHOLD:
            logger.warning(
                f"auth_cost 耗时: {elapsed:.3f}s, plugin={plugin.module}",
                LOGGER_COMMAND,
                session=session,
            )
