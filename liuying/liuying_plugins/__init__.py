from datetime import datetime

import nonebot
from nonebot.adapters import Bot
from nonebot.drivers import Driver
from sqlalchemy.exc import IntegrityError

from liuying.models._log.bot_connect_log import BotConnectLog
from liuying.models._bot import BotConsole
from liuying.utils.log import logger
from liuying.utils.platform import PlatformUtils

driver: Driver = nonebot.get_driver()


@driver.on_bot_connect
async def _(bot: Bot) -> None:
    """Bot连接时创建BotConsole记录

    参数:
        bot: Bot
    """
    logger.debug(f"Bot: {bot.self_id} 建立连接...")
    await BotConnectLog.create(
        bot_id=bot.self_id,
        platform=str(bot.adapter),
        connect_time=datetime.now(),
        type=1,
    )
    if not await BotConsole.filter(bot_id=bot.self_id).exists():
        try:
            await BotConsole.create(
                bot_id=bot.self_id, platform=PlatformUtils.get_platform(bot)
            )
        except IntegrityError as e:
            logger.warning(f"记录bot: {bot.self_id} 数据已存在...", e=e)

@driver.on_bot_disconnect
async def _(bot: Bot):
    logger.debug(f"Bot: {bot.self_id} 断开连接...")
    try:
        await BotConnectLog.create(
            bot_id=bot.self_id,
            platform=str(bot.adapter),
            connect_time=datetime.now(),
            type=0,
        )
    except Exception as e:
        logger.warning(
            f"记录bot: {bot.self_id} 断开连接失败", e=e
            )
