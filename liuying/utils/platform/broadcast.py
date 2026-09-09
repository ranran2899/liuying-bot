import asyncio
from collections.abc import Awaitable, Callable
import random
from typing import cast

import nonebot
from nonebot.adapters import Bot
from nonebot.utils import is_coroutine_callable
from nonebot_plugin_alconna.uniseg import UniMessage

from liuying.models._group import GroupConfig, GroupConsole
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils
from liuying.utils.platform.group import GroupUtils
from liuying.utils.platform.helper import PlatformUtils


class BroadcastEngine:
    """
    广播引擎
    
    用于发送消息到指定群聊或所有群聊或指定bot或所有bot或指定平台或所有平台的bot
    """
    def __init__(
        self,
        message: str | UniMessage,
        bot: Bot | list[Bot] | None = None,
        bot_id: str | set[str] | None = None,
        ignore_group: list[str] | None = None,
        check_func: Callable[[Bot, str], Awaitable] | None = None,
        log_cmd: str | None = None,
        platform: str | None = None,
    ):
        """广播引擎

        参数:
            message: 广播消息内容
            bot: 指定bot对象.
            bot_id: 指定bot id.
            ignore_group: 忽略群聊列表.
            check_func: 发送前对群聊检测方法，判断是否发送.
            log_cmd: 日志标记.
            platform: 指定平台.

        异常:
            ValueError: 没有可用的Bot对象
        """
        self.message = MessageUtils.build_message(message)
        self.ignore_group = ignore_group or []
        self.check_func = check_func
        self.log_cmd = log_cmd
        self.platform = platform
        self.bot_list: list[Bot] = []
        self.count = 0
        if bot:
            self.bot_list = [bot] if isinstance(bot, Bot) else bot
        if bot_id:
            bids = {bot_id} if isinstance(bot_id, str) else bot_id
            for bid in bids:
                try:
                    self.bot_list.append(nonebot.get_bot(bid))
                except KeyError:
                    logger.warning(
                        f"Bot:{bid} 对象未连接或不存在", command=log_cmd
                    )
        if not self.bot_list:
            try:
                bot = nonebot.get_bot()
                self.bot_list.append(bot)
                logger.warning(
                    f"广播任务未传入Bot对象，使用默认Bot {bot.self_id}",
                    command=log_cmd,
                )
            except Exception as e:
                raise ValueError("当前没有可用的Bot对象...", log_cmd) from e

    async def call_check(self, bot: Bot, group_id: str) -> bool:
        """运行发送检测函数

        参数:
            bot: Bot
            group_id: 群组id

        返回:
            bool: 是否发送
        """
        if not self.check_func:
            return True
        is_run = (
            await self.check_func(bot, group_id)
            if is_coroutine_callable(self.check_func)
            else self.check_func(bot, group_id)
        )
        return cast(bool, is_run)

    async def __send_message(self, bot: Bot, group: GroupConsole):
        """群组发送消息

        参数:
            bot: Bot
            group: GroupConsole
        """
        key = f"{group.group_id}:{group.channel_id}"
        if not await self.call_check(bot, group.group_id):
            logger.debug(
                "广播方法检测运行方法为 False, 已跳过该群组...",
                command=self.log_cmd,
                group_id=group.group_id,
            )
            return
        if not await GroupConfig.is_proactive_allowed(group.group_id):
            logger.debug(
                "群聊已关闭主动消息, 跳过该群组...",
                command=self.log_cmd,
                group_id=group.group_id,
            )
            return
        if target := PlatformUtils.get_target(
            group_id=group.group_id,
            channel_id=group.channel_id,
        ):
            self.ignore_group.append(key)
            await MessageUtils.build_message(self.message).send(target, bot)
            logger.debug("广播消息发送成功...", command=self.log_cmd, target=key)
        else:
            logger.warning(
                "广播消息获取Target失败...", command=self.log_cmd, target=key
            )

    async def broadcast(self) -> int:
        """广播消息

        返回:
            int: 成功发送次数
        """
        for bot in self.bot_list:
            if self.platform and self.platform != PlatformUtils.get_platform(bot):
                continue
            group_list, _ = await GroupUtils.get_group_list(bot)
            if not group_list:
                continue
            for group in group_list:
                if (
                    group.group_id in self.ignore_group
                    or group.channel_id in self.ignore_group
                ):
                    continue
                try:
                    await self.__send_message(bot, group)
                    await asyncio.sleep(random.randint(1, 3))
                    self.count += 1
                except Exception as e:
                    logger.warning(
                        "广播消息发送失败",
                        command=self.log_cmd,
                        target=group.group_id,
                        e=e,
                    )
        return self.count


async def broadcast_group(
    message: str | UniMessage,
    bot: Bot | list[Bot] | None = None,
    bot_id: str | set[str] | None = None,
    ignore_group: list[str] | None = None,
    check_func: Callable[[Bot, str], Awaitable] | None = None,
    log_cmd: str | None = None,
    platform: str | None = None,
) -> int:
    """获取所有Bot或指定Bot对象广播群聊

    参数:
        message: 广播消息内容
        bot: 指定bot对象.
        bot_id: 指定bot id.
        ignore_group: 忽略群聊列表.
        check_func: 发送前对群聊检测方法，判断是否发送.
        log_cmd: 日志标记.
        platform: 指定平台

    返回:
        int: 成功发送次数
    """
    if not message.strip():
        raise ValueError("群聊广播消息不能为空...")
    return await BroadcastEngine(
        message=message,
        bot=bot,
        bot_id=bot_id,
        ignore_group=ignore_group,
        check_func=check_func,
        log_cmd=log_cmd,
        platform=platform,
    ).broadcast()
