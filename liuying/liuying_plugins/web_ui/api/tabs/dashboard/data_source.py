import asyncio
from datetime import datetime, timedelta
import time

import nonebot
from nonebot.adapters import Bot
from nonebot.drivers import Driver
from sqlalchemy import func

from liuying.liuying_plugins.web_ui.utils import get_bot_login_info
from liuying.models._log.bot_connect_log import BotConnectLog
from liuying.models.chat_history import ChatHistory
from liuying.models.statistics import Statistics
from liuying.utils.log import logger
from liuying.utils.manager.priority_manager import PriorityLifecycle
from liuying.utils.platform import PlatformUtils

from ....base_model import BaseResultModel, QueryModel
from ..main.data_source import bot_live
from .model import (
    AllChatAndCallCount,
    BotConnectLogInfo,
    BotInfo,
    ChatCallMonthCount,
    QueryChatCallCount,
)

driver: Driver = nonebot.get_driver()


CONNECT_TIME = 0


@PriorityLifecycle.on_startup(priority=5)
async def _():
    global CONNECT_TIME
    CONNECT_TIME = int(time.time())


class ApiDataSource:
    @classmethod
    async def __build_bot_info(cls, bot: Bot) -> BotInfo:
        """构建Bot信息

        参数:
            bot: Bot

        返回:
            BotInfo: Bot信息
        """
        platform = PlatformUtils.get_platform(bot) or ""
        nickname, ava_url = await get_bot_login_info(bot, bot.self_id)
        bot_info = BotInfo(
            self_id=bot.self_id, nickname=nickname, ava_url=ava_url, platform=platform
        )
        try:
            group, friend = await asyncio.gather(
                PlatformUtils.get_group_list(bot, True),
                PlatformUtils.get_friend_list(bot),
            )
            bot_info.group_count = len(group[0])
            bot_info.friend_count = len(friend[0])
        except Exception as e:
            logger.warning("获取bot好友/群组信息失败...", command="WebUi", e=e)
            bot_info.group_count = 0
            bot_info.friend_count = 0
        bot_info.day_call = await Statistics.count_records(
            bot_id=bot.self_id, days=1
        )
        bot_info.received_messages = await ChatHistory.count_records(
            bot_id=bot_info.self_id, days=1
        )
        bot_info.connect_time = bot_live.get(bot.self_id) or 0
        if bot_info.connect_time:
            connect_date = datetime.fromtimestamp(bot_info.connect_time)
            bot_info.connect_date = connect_date.strftime("%Y-%m-%d %H:%M:%S")
        return bot_info

    @classmethod
    async def get_bot_list(cls) -> list[BotInfo]:
        """获取bot列表

        返回:
            list[BotInfo]: Bot列表
        """
        bot_list: list[BotInfo] = []
        for _, bot in nonebot.get_bots().items():
            bot_list.append(await cls.__build_bot_info(bot))
        return bot_list

    @classmethod
    async def get_chat_and_call_count(cls, bot_id: str | None) -> QueryChatCallCount:
        """获取今日聊天和调用次数

        参数:
            bot_id: bot id

        返回:
            QueryChatCallCount: 数据内容
        """
        return QueryChatCallCount(
            chat_num=await ChatHistory.count_records(bot_id=bot_id),
            chat_day=await ChatHistory.count_records(bot_id=bot_id, days=1),
            call_num=await Statistics.count_records(bot_id=bot_id),
            call_day=await Statistics.count_records(bot_id=bot_id, days=1),
        )

    @classmethod
    async def get_all_chat_and_call_count(
        cls, bot_id: str | None
    ) -> AllChatAndCallCount:
        """获取全部聊天和调用记录

        参数:
            bot_id: bot id

        返回:
            AllChatAndCallCount: 数据内容
        """
        return AllChatAndCallCount(
            chat_week=await ChatHistory.count_records(bot_id=bot_id, days=7),
            chat_month=await ChatHistory.count_records(bot_id=bot_id, days=30),
            chat_year=await ChatHistory.count_records(bot_id=bot_id, days=365),
            call_week=await Statistics.count_records(bot_id=bot_id, days=7),
            call_month=await Statistics.count_records(bot_id=bot_id, days=30),
            call_year=await Statistics.count_records(bot_id=bot_id, days=365),
        )

    @classmethod
    async def get_chat_and_call_month(cls, bot_id: str | None) -> ChatCallMonthCount:
        """获取一个月内的调用/消息记录次数，并根据日期对数据填充0

        参数:
            bot_id: bot id

        返回:
            ChatCallMonthCount: 数据内容
        """
        now = datetime.now()
        filter_date = now - timedelta(days=30, hours=now.hour, minutes=now.minute)
        chat_query = ChatHistory
        call_query = Statistics
        if bot_id:
            chat_query = chat_query.filter(bot_id=bot_id)
            call_query = call_query.filter(bot_id=bot_id)
        # 使用 label() 创建命名列对象，避免 SQLAlchemy 2.0 字符串列引用错误
        chat_date_col = func.date(ChatHistory.create_time).label("date")
        chat_count_col = func.count(ChatHistory.id).label("count")
        call_date_col = func.date(Statistics.create_time).label("date")
        call_count_col = func.count(Statistics.id).label("count")
        chat_date_list = (
            await chat_query.filter(create_time__gte=filter_date)
            .annotate(date=chat_date_col, count=chat_count_col)
            .group_by(chat_date_col)
            .values(chat_date_col, chat_count_col)
            .all()
        )
        call_date_list = (
            await call_query.filter(create_time__gte=filter_date)
            .annotate(date=call_date_col, count=call_count_col)
            .group_by(call_date_col)
            .values(call_date_col, call_count_col)
            .all()
        )
        date_list = []
        chat_count_list = []
        call_count_list = []
        chat_date2cnt = {str(row[0]): row[1] for row in chat_date_list}
        call_date2cnt = {str(row[0]): row[1] for row in call_date_list}
        date = now.date()
        for _ in range(30):
            if str(date) in chat_date2cnt:
                chat_count_list.append(chat_date2cnt[str(date)])
            else:
                chat_count_list.append(0)
            if str(date) in call_date2cnt:
                call_count_list.append(call_date2cnt[str(date)])
            else:
                call_count_list.append(0)
            date_list.append(str(date)[5:])
            date -= timedelta(days=1)
        chat_count_list.reverse()
        call_count_list.reverse()
        date_list.reverse()
        return ChatCallMonthCount(
            chat=chat_count_list, call=call_count_list, date=date_list
        )

    @classmethod
    async def get_connect_log(cls, query: QueryModel) -> BaseResultModel:
        """获取bot连接日志

        参数:
            query: 查询模型

        返回:
            BaseResultModel: 数据内容
        """
        total = await BotConnectLog.filter().count()
        if total % query.size:
            total += 1
        data = (
            await BotConnectLog.filter()
            .order_by("-id")
            .offset((query.index - 1) * query.size)
            .limit(query.size)
            .all()
        )
        result_list = []
        for v in data:
            v.connect_time = v.connect_time.replace(tzinfo=None).replace(microsecond=0)
            result_list.append(
                BotConnectLogInfo(
                    bot_id=v.bot_id, connect_time=v.connect_time, type=v.type
                )
            )
        return BaseResultModel(total=total, data=result_list)
