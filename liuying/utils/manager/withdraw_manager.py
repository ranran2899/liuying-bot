import asyncio
from typing import ClassVar

from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import Bot as v11Bot
from nonebot.adapters.onebot.v12 import Bot as v12Bot

from liuying.utils.log import logger


class WithdrawManager:
    """撤回消息管理器"""
    _data: ClassVar[dict[int, tuple[Bot, str | int, int]]] = {}
    _index: ClassVar[int] = 0

    @classmethod
    def append(
        cls,
        bot: Bot,
        message_id: str | int,
        time: int,
    ):
        """添加待撤回消息

        参数:
            bot: 机器人实例
            message_id: 消息ID
            time: 撤回时间（秒）
        """
        cls._data[cls._index] = (bot, message_id, time)
        cls._index += 1

    @classmethod
    def remove(cls, index: int):
        """移除待撤回消息

        参数:
            index: 消息索引
        """
        if index in cls._data:
            del cls._data[index]

    @classmethod
    async def withdraw_message(
        cls,
        bot: Bot,
        message_id: str | int,
        time: int | None = None,
    ):
        """撤回消息

        参数:
            bot: 机器人实例
            message_id: 消息ID
            time: 撤回时间（秒），默认 None 表示立即撤回
        """
        if time:
            logger.debug(
                f"将在 {time}秒 内撤回消息ID: {message_id}", "WithdrawManager"
            )
            await asyncio.sleep(time)
        match bot:
            case v11Bot():
                logger.debug(f"v11Bot 撤回消息ID: {message_id}", "WithdrawManager")
                await bot.delete_msg(message_id=int(message_id))
            case v12Bot():
                logger.debug(f"v12Bot 撤回消息ID: {message_id}", "WithdrawManager")
                await bot.delete_message(message_id=str(message_id))
