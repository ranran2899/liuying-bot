from nonebot_plugin_alconna import AlconnaMatch, Match
from nonebot_plugin_uninfo import Uninfo

from liuying.models._bot import BotConsole
from liuying.services.log import logger
from liuying.utils.message import MessageUtils

from .command import bot_manage


@bot_manage.assign("bot_switch.enable")
async def enable_bot_switch(
    session: Uninfo,
    bot_id: Match[str] = AlconnaMatch("bot_id"),
):
    """启用bot开关"""
    _bot_id = bot_id.result if bot_id.available else session.self_id

    logger.info(
        f"开启 {_bot_id} ",
        "bot_manage.bot_switch.enable",
        session=session,
    )
    try:
        await BotConsole.set_bot_status(True, _bot_id)
    except ValueError:
        await MessageUtils.build_message(f"bot_id {_bot_id} 不存在").finish()

    await MessageUtils.build_message(f"已开启 {_bot_id} ").finish()


@bot_manage.assign("bot_switch.disable")
async def disable_bot_switch(
    session: Uninfo,
    bot_id: Match[str] = AlconnaMatch("bot_id"),
):
    """禁用bot开关"""
    _bot_id = bot_id.result if bot_id.available else session.self_id

    logger.info(
        f"禁用 {_bot_id} ",
        "bot_manage.bot_switch.disable",
        session=session,
    )
    try:
        await BotConsole.set_bot_status(False, _bot_id)
    except ValueError:
        await MessageUtils.build_message(f"bot_id {_bot_id} 不存在").finish()

    await MessageUtils.build_message(f"已禁用 {_bot_id} ").finish()
