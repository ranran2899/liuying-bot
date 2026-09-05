"""聊天记录插件 - 记录消息并统计群发言排行"""

from nonebot import on_message
from nonebot.adapters import Event
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, Match, UniMsg, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.config import Config
from liuying.configs.utils import Command, PluginExtraData, RegisterConfig
from liuying.utils.enum import PluginType
from liuying.utils.manager import PriorityLifecycle
from liuying.utils.message import MessageUtils
from liuying.utils.rules import admin_check

from .data_source import ChatHistoryManager
from .recorder import ChatHistoryHook

__plugin_meta__ = PluginMetadata(
    name="热门群聊",
    description="记录聊天消息，统计各群发言次数排行",
    usage="""
    usage：
    指令：
        热门群聊 [天数] : 查看群发言次数排行，默认统计全部
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.2",
        plugin_type=PluginType.SUPER_AND_ADMIN,
        menu_type="统计",
        aliases={"群发言统计", "群活跃统计"},
        commands=[
            Command(
                command="热门群聊",
                params=["天数?"],
                description="统计各群发言次数排行（图片）",
            ),
        ],
        configs=[
            RegisterConfig(
                key="CHAT_HISTORY_ENABLE",
                value=True,
                help="是否启用聊天记录",
                default_value=True,
                type=bool,
            ),
            RegisterConfig(
                key="CHAT_HISTORY_BATCH_INTERVAL",
                value=60,
                help="批量写入聊天记录的间隔（秒）",
                default_value=60,
                type=int,
            ),
            RegisterConfig(
                key="CHAT_HISTORY_BATCH_SIZE",
                value=100,
                help="批量写入聊天记录的最大数量",
                default_value=100,
                type=int,
            ),
        ],
    ).to_dict(),
)

@PriorityLifecycle.on_startup(priority=10)
async def _start_chat_history_queue():
    """启动聊天记录队列处理"""
    await ChatHistoryHook.start(
        Config.get_config("chat_history", "CHAT_HISTORY_BATCH_INTERVAL") or 60,
        Config.get_config("chat_history", "CHAT_HISTORY_BATCH_SIZE") or 100,
    )


@PriorityLifecycle.on_shutdown(priority=10)
async def _stop_chat_history_queue():
    """停止聊天记录队列处理"""
    await ChatHistoryHook.stop()


_record_matcher = on_message(priority=10, block=False)


@_record_matcher.handle()
async def _(session: Uninfo, event: Event, message: UniMsg):
    """记录聊天消息"""
    ChatHistoryHook.record(session, event, message)


_hot_matcher = on_alconna(
    Alconna("热门群聊", Args["days?", int]),
    aliases={"群发言统计", "群活跃统计"},
    priority=5,
    rule=admin_check(6),
    block=True,
)


@_hot_matcher.handle()
async def _(days: Match[int]):
    """处理热门群聊排行命令"""
    result = await ChatHistoryManager.get_hot_groups(
        days.result if days.available else None
    )

    match result:
        case str():
            await MessageUtils.build_message(result).finish(reply_to=True)
        case _:
            await MessageUtils.build_message(result).send()
