import asyncio
from datetime import datetime
from pathlib import Path
import time

import nonebot
from nonebot.adapters import Bot
from nonebot.drivers import Driver

from liuying.models._bot import BotConsole
from liuying.models._group import GroupConsole
from liuying.models._log.bot_connect_log import BotConnectLog
from liuying.models.chat_history import ChatHistory
from liuying.models.plugin_info import PluginInfo
from liuying.models.statistics import Statistics
from liuying.models.task_info import TaskInfo
from liuying.utils.common_utils import CommonUtils
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.platform import PlatformUtils

from ....config import GROUP_AVA_URL, QueryDateType
from .model import (
    ActiveGroup,
    BaseInfo,
    BotBlockModule,
    HotPlugin,
    QueryCount,
    TemplateBaseInfo,
)

driver: Driver = nonebot.get_driver()


class BotLive:
    def __init__(self):
        self._data: dict[str, int] = {}

    def add(self, bot_id: str):
        self._data[bot_id] = int(time.time())

    def get(self, bot_id: str) -> int | None:
        return self._data.get(bot_id)

    def remove(self, bot_id: str):
        if bot_id in self._data:
            del self._data[bot_id]


bot_live = BotLive()


@driver.on_bot_connect
async def _(bot: Bot):
    bot_live.add(bot.self_id)


@driver.on_bot_disconnect
async def _(bot: Bot):
    bot_live.remove(bot.self_id)


class ApiDataSource:
    @classmethod
    async def __build_bot_info(cls, bot: Bot) -> TemplateBaseInfo:
        """构建bot信息

        参数:
            bot: bot实例

        返回:
            TemplateBaseInfo: bot信息
        """
        nickname, ava_url = await PlatformUtils.get_bot_info(bot)
        return TemplateBaseInfo(
            bot=bot,
            self_id=bot.self_id,
            nickname=nickname,
            ava_url=ava_url,
        )

    @classmethod
    def __get_bot_version(cls) -> str:
        """获取bot版本

        返回:
            str | None: 版本
        """
        version_file = Path() / "__version__"
        if version_file.exists():
            with version_file.open(encoding="utf-8") as f:
                if text := f.read():
                    return text.replace("__version__: ", "").strip()
        return "unknown"

    @classmethod
    async def __init_bot_base_data(cls, select_bot: TemplateBaseInfo):
        """初始化bot的基础数据

        参数:
            select_bot: bot
        """
        # 今日累计接收消息
        select_bot.received_messages = await ChatHistory.count_records(
            bot_id=select_bot.self_id, days=1
        )
        # 群聊数量
        try:
            select_bot.group_count = len(
                (await PlatformUtils.get_group_list(select_bot.bot, True))[0]
            )
            # 好友数量
            select_bot.friend_count = len(
                (await PlatformUtils.get_friend_list(select_bot.bot))[0]
            )
        except Exception as e:
            logger.warning("获取bot好友/群组数量失败...", command="WebUi", e=e)
            select_bot.group_count = 0
            select_bot.friend_count = 0
        select_bot.status = await BotConsole.get_bot_status(select_bot.self_id)
        # 连接时间
        select_bot.connect_time = bot_live.get(select_bot.self_id) or 0
        if select_bot.connect_time:
            connect_date = datetime.fromtimestamp(select_bot.connect_time)
            select_bot.connect_date = connect_date.strftime("%Y-%m-%d %H:%M:%S")
        select_bot.version = cls.__get_bot_version()
        select_bot.day_call = await Statistics.count_records(days=1)
        select_bot.connect_count = await BotConnectLog.filter(
            bot_id=select_bot.self_id
        ).count()

    @classmethod
    async def get_base_info(cls, bot_id: str | None) -> list[BaseInfo] | None:
        """获取bot信息

        参数:
            bot_id: bot id

        返回:
            list[BaseInfo] | None: bot列表
        """
        bots = nonebot.get_bots()
        if not bots:
            return None
        select_bot: BaseInfo
        bot_list = await asyncio.gather(
            *[cls.__build_bot_info(bot) for _, bot in bots.items()]
        )
        # 获取指定qq号的bot信息，若无指定   则获取第一个
        if _bl := [b for b in bot_list if b.self_id == bot_id]:
            select_bot = _bl[0]
        else:
            select_bot = bot_list[0]
        await cls.__init_bot_base_data(select_bot)
        for bot in bot_list:
            bot.bot = None  # type: ignore
        select_bot.is_select = True
        return [BaseInfo(**e.to_dict()) for e in bot_list]

    @classmethod
    async def get_all_chat_count(cls, bot_id: str | None) -> QueryCount:
        """获取年/月/周/日聊天次数

        参数:
            bot_id: bot id

        返回:
            QueryCount: 数据内容
        """
        return QueryCount(
            num=await ChatHistory.count_records(bot_id=bot_id),
            day=await ChatHistory.count_records(bot_id=bot_id, days=1),
            week=await ChatHistory.count_records(bot_id=bot_id, days=7),
            month=await ChatHistory.count_records(bot_id=bot_id, days=30),
            year=await ChatHistory.count_records(bot_id=bot_id, days=365),
        )

    @classmethod
    async def get_all_call_count(cls, bot_id: str | None) -> QueryCount:
        """获取年/月/周/日调用次数

        参数:
            bot_id: bot id

        返回:
            QueryCount: 数据内容
        """
        return QueryCount(
            num=await Statistics.count_records(bot_id=bot_id),
            day=await Statistics.count_records(bot_id=bot_id, days=1),
            week=await Statistics.count_records(bot_id=bot_id, days=7),
            month=await Statistics.count_records(bot_id=bot_id, days=30),
            year=await Statistics.count_records(bot_id=bot_id, days=365),
        )

    @classmethod
    async def get_active_group(
        cls, date_type: QueryDateType | None = None, bot_id: str | None = None
    ) -> list[ActiveGroup]:
        """获取活跃群组

        参数:
            date_type: 日期类型.
            bot_id: bot id.

        返回:
            list[ActiveGroup]: 活跃群组列表
        """
        days_map = {
            QueryDateType.DAY: 1,
            QueryDateType.WEEK: 7,
            QueryDateType.MONTH: 30,
            QueryDateType.YEAR: 365,
        }
        days = days_map.get(date_type)
        data_list = await ChatHistory.get_active_groups(
            bot_id=bot_id, days=days, limit=5
        )
        id2name = {}
        if data_list:
            if info_list := await GroupConsole.filter(
                group_id__in=[x[0] for x in data_list]
            ).all():
                for group_info in info_list:
                    id2name[group_info.group_id] = group_info.group_name
        active_group_list = [
            ActiveGroup(
                group_id=data[0],
                name=id2name.get(data[0]) or data[0],
                chat_num=data[1],
                ava_img=GROUP_AVA_URL.format(data[0], data[0]),
            )
            for data in data_list
        ]
        active_group_list = sorted(
            active_group_list, key=lambda x: x.chat_num, reverse=True
        )
        if len(active_group_list) > 5:
            active_group_list = active_group_list[:5]
        return active_group_list

    @classmethod
    async def get_hot_plugin(
        cls, date_type: QueryDateType | None = None, bot_id: str | None = None
    ) -> list[HotPlugin]:
        """获取热门插件

        参数:
            date_type: 日期类型.
            bot_id: bot id.

        返回:
            list[HotPlugin]: 热门插件列表
        """
        days_map = {
            QueryDateType.DAY: 1,
            QueryDateType.WEEK: 7,
            QueryDateType.MONTH: 30,
            QueryDateType.YEAR: 365,
        }
        days = days_map.get(date_type)
        data_list = await Statistics.get_plugin_usage_count(
            bot_id=bot_id, days=days, limit=5
        )
        module_list = [x[0] for x in data_list]
        module2name = await PluginInfo.get_name_map(module_list)
        return [
            HotPlugin(
                module=module,
                name=module2name.get(module) or module,
                count=count,
            )
            for module, count in data_list
        ]

    @classmethod
    async def get_bot_block_module(cls, bot_id: str) -> BotBlockModule | None:
        """获取bot层面的禁用模块

        参数:
            bot_id: bot id

        返回:
            BotBlockModule | None: 数据内容
        """
        bot_data = await BotConsole.filter(bot_id=bot_id).first()
        if not bot_data:
            return None
        block_tasks = []
        block_plugins = []
        all_plugins_obj = await PluginInfo.filter(
            load_status=True, plugin_type=PluginType.NORMAL
        ).all()
        all_plugins = [{"module": p.module, "name": p.name} for p in all_plugins_obj]
        all_task_obj = await TaskInfo.filter().all()
        all_task = [{"module": t.module, "name": t.name} for t in all_task_obj]
        if bot_data.block_tasks:
            tasks = CommonUtils.convert_module_format(bot_data.block_tasks)
            block_tasks = [t["module"] for t in all_task if t["module"] in tasks]
        if bot_data.block_plugins:
            plugins = CommonUtils.convert_module_format(bot_data.block_plugins)
            block_plugins = [t["module"] for t in all_plugins if t["module"] in plugins]
        return BotBlockModule(
            bot_id=bot_id,
            block_tasks=block_tasks,
            block_plugins=block_plugins,
            all_plugins=all_plugins,
            all_tasks=all_task,
        )
