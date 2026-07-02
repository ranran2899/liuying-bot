import asyncio

from nonebot.adapters import Bot
from nonebot.matcher import Matcher
from nonebot.message import run_postprocessor

from liuying.utils.manager.withdraw_manager import WithdrawManager


@run_postprocessor
async def _(matcher: Matcher, exception: Exception | None, bot: Bot):
    """处理消息撤回"""
    tasks = [
        WithdrawManager.withdraw_message(bot, msg_id, time_val)
        for bot, msg_id, time_val in WithdrawManager._data.values()
    ]

    WithdrawManager._data.clear()

    if tasks:
        await asyncio.gather(*tasks)
