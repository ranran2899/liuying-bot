import re
import asyncio

import nonebot
from nonebot import on_regex
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import GROUP, GroupMessageEvent, Event
from nonebot.plugin import PluginMetadata

from liuying.utils.apscheduler import task_manager

from liuying.models._bot import BotConsole
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils
from liuying.configs.utils.models import PluginExtraData, Command

from .models import ZanSubscribe

__plugin_meta__ = PluginMetadata(
    name="自动点赞订阅赞",
    description="点赞、订阅赞功能，每天 0 点定时点赞！轻量、高效、便捷的小插件！",
    usage="""
    点赞功能
    指令:
        点赞我
        超赞我
        赞市我
        超赞市我
        订阅赞
        订阅超赞
        取消订阅赞
        取消订阅超赞
        赞 [QQ号]
        超赞 [QQ号]
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.2",
        plugin_type=PluginType.NORMAL,
        menu_type="功能",
        commands=[
            Command(command="点赞我"),
            Command(command="超赞我"),
            Command(command="赞市我"),
            Command(command="超赞市我"),
            Command(command="订阅赞"),
            Command(command="订阅超赞"),
            Command(command="取消订阅赞"),
            Command(command="取消订阅超赞"),
            Command(command="赞", params=["QQ号"]),
            Command(command="超赞", params=["QQ号"]),
        ],
    ).to_dict(),
)

zan = on_regex("^(超|赞)(市|)我$", permission=GROUP)
zan_sub = on_regex("^订阅(超|赞)$", permission=GROUP)
zan_other = on_regex(r"^(超|赞)(市|)(你|他|她|它|TA|)\s*(.*)$", permission=GROUP)
zan_unsub = on_regex("^取消订阅(超|赞)$", permission=GROUP)


async def dian_zan(bot: Bot, user_id: int) -> int:
    """
    核心函数，给指定用户点赞

    参数:
        bot: Bot对象
        user_id: 用户ID

    返回:
        int: 点赞次数
    """
    count = 0
    try:
        for _ in range(5):
            await bot.send_like(user_id=user_id, times=10)
            count += 10
    except Exception as e:
        logger.error(f"给 {user_id} 点赞失败: {e}")
        pass
    return count


@zan_other.handle()
async def zan_other_(bot: Bot, event: Event):
    """处理给他人点赞事件"""
    message = str(event.get_message()).strip()
    match_result = re.search(r"[1-9]([0-9]{5,11})", message)
    if not match_result:
        return

    user_id = int(match_result.group(0))
    if user_id:
        count = await dian_zan(bot, user_id)
        if count > 0:
            await MessageUtils.build_message(f"已经给 {user_id} 点了 {count} 个赞！").finish(reply_to=True)
        else:
            await MessageUtils.build_message("我给不了他更多了哟~").finish(reply_to=True)
    else:
        await MessageUtils.build_message("未指定有效的QQ号或@用户").finish(reply_to=True)


@zan.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    """处理点赞事件"""
    count = await dian_zan(bot, event.user_id)
    if count != 0:
        await MessageUtils.build_message(f"已经给你点了{count}个赞！如果失败可以添加好友再试！").send(reply_to=True)
    else:
        await MessageUtils.build_message("我给不了你更多了哟~").finish(reply_to=True)


@zan_sub.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    """处理订阅点赞事件，记录触发订阅的机器人"""
    user_id = event.user_id
    bot_id = str(bot.self_id)
    if not await ZanSubscribe.is_subscribed(str(user_id), bot_id):
        if await ZanSubscribe.add_subscriber(str(user_id), bot_id):
            await MessageUtils.build_message("订阅成功了哟~").finish(reply_to=True)
        else:
            await MessageUtils.build_message("订阅失败，请稍后再试~").finish(reply_to=True)
    else:
        await MessageUtils.build_message("你已经订阅过了哟~").finish(reply_to=True)


@zan_unsub.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    """处理取消订阅点赞事件，移除当前机器人的订阅"""
    user_id = event.user_id
    bot_id = str(bot.self_id)
    if await ZanSubscribe.is_subscribed(str(user_id), bot_id):
        if await ZanSubscribe.remove_subscriber(str(user_id), bot_id):
            await MessageUtils.build_message("已成功取消订阅点赞！").finish(reply_to=True)
        else:
            await MessageUtils.build_message("取消订阅失败，请稍后再试~").finish(reply_to=True)
    else:
        await MessageUtils.build_message("你还没有订阅过呢~").finish(reply_to=True)


@task_manager.cron_task("job_subscribed_likes", hour=0, minute=1)
async def run_subscribed_likes():
    """处理每日点赞逻辑，遍历所有在线机器人独立执行订阅点赞"""
    online_bots = nonebot.get_bots()
    if not online_bots:
        return

    # 转换为列表避免遍历时字典被修改
    # （BotConsole.get_bot_status 可能会更新 bots 字典）
    bot_items = list(online_bots.items())

    for bot_id, bot in bot_items:
        try:
            if not await BotConsole.get_bot_status(bot_id):
                continue

            sub_users = await ZanSubscribe.get_subscribers_by_bot(bot_id)
            if not sub_users:
                continue

            success_count = 0
            for user_id in sub_users:
                count = await dian_zan(bot, int(user_id))
                if count > 0:
                    success_count += 1
                await asyncio.sleep(5)

            if success_count > 0:
                logger.info(
                    f"[订阅赞] Bot:{bot_id} "
                    f"完成 {success_count}/{len(sub_users)} 个用户点赞"
                )
        except Exception as e:
            logger.error(f"[订阅赞] Bot:{bot_id} 执行异常: {e}")
