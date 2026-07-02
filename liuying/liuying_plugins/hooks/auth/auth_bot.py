import asyncio
import time

from liuying.models._bot import BotConsole
from liuying.models.plugin_info import PluginInfo
from liuying.services.data_access import DataAccess
from liuying.services.liuying_db.config import DB_TIMEOUT_SECONDS
from liuying.utils.common_utils import CommonUtils
from liuying.utils.log import logger

from .config import LOGGER_COMMAND, WARNING_THRESHOLD
from .exception import SkipPluginException


async def auth_bot(plugin: PluginInfo, bot_id: str):
    """bot层面的权限检查

    参数:
        plugin: PluginInfo
        bot_id: bot id

    异常:
        SkipPluginException: Bot不存在或休眠中
        SkipPluginException: Bot插件被禁用
    """
    start_time = time.time()

    try:
        bot_dao = DataAccess(BotConsole)

        try:
            bot: BotConsole | None = await asyncio.wait_for(
                bot_dao.safe_get_or_none(bot_id=bot_id), timeout=DB_TIMEOUT_SECONDS
            )
        except TimeoutError:
            logger.error(f"查询Bot信息超时: bot_id={bot_id}", LOGGER_COMMAND)
            return

        match (bot, bot.status if bot else False):
            case (None, _) | (_, False):
                raise SkipPluginException("Bot不存在或休眠中阻断权限检测...")

        if CommonUtils.format(plugin.module) in bot.block_plugins:
            raise SkipPluginException(
                f"Bot插件 {plugin.name}({plugin.module}) 权限检查结果为关闭..."
            )
    finally:
        elapsed = time.time() - start_time
        if elapsed > WARNING_THRESHOLD:
            logger.warning(
                f"auth_bot 耗时: {elapsed:.3f}s, "
                f"bot_id={bot_id}, plugin={plugin.module}",
                LOGGER_COMMAND,
            )
