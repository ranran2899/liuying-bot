import asyncio
from typing import ClassVar

from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import Bot as v11Bot
from nonebot.adapters.onebot.v12 import Bot as v12Bot
from nonebot.adapters.qq import Bot as qqBot

from liuying.utils.log import logger

type WithdrawEntry = tuple[Bot, str | int, int, str | None, bool]
"""撤回记录: (机器人实例, 消息ID, 撤回时间, QQ官方适配器openid, 是否群聊)"""


class WithdrawManager:
    """撤回消息管理器"""
    _data: ClassVar[dict[int, WithdrawEntry]] = {}
    _index: ClassVar[int] = 0

    @classmethod
    def append(
        cls,
        bot: Bot,
        message_id: str | int,
        time: int,
        openid: str | None = None,
        is_group: bool = False,
    ):
        """添加待撤回消息

        参数:
            bot: 机器人实例
            message_id: 消息ID
            time: 撤回时间（秒）
            openid: QQ官方适配器的群或用户openid
            is_group: openid是否为群聊标识
        """
        cls._data[cls._index] = (bot, message_id, time, openid, is_group)
        cls._index += 1

    @classmethod
    def remove(cls, index: int):
        """移除待撤回消息

        参数:
            index: 消息索引
        """
        cls._data.pop(index, None)

    @classmethod
    async def withdraw_message(
        cls,
        bot: Bot,
        message_id: str | int,
        time: int | None = None,
        openid: str | None = None,
        is_group: bool = False,
    ):
        """撤回消息

        参数:
            bot: 机器人实例
            message_id: 消息ID
            time: 撤回时间（秒），默认 None 表示立即撤回
            openid: QQ官方适配器的群或用户openid
            is_group: openid是否为群聊标识
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
            case qqBot() if openid:
                logger.debug(f"qqBot 撤回消息ID: {message_id}", "WithdrawManager")
                if is_group:
                    await bot.delete_group_message(
                        group_openid=openid, message_id=str(message_id)
                    )
                else:
                    await bot.delete_c2c_message(
                        openid=openid, message_id=str(message_id)
                    )
