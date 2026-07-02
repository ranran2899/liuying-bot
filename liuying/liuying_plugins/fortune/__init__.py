"""今日运势插件 - 每日随机运势"""

from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import Command, PluginExtraData
from liuying.utils.enum import PluginType
from liuying.utils.log import logger

from .fortune import FortuneHandler

__plugin_meta__ = PluginMetadata(
    name="今日运势",
    description="每日随机运势",
    usage="""
    今日运势
    刷新今日运势 (超级用户)
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.1",
        plugin_type=PluginType.NORMAL,
        menu_type="娱乐",
        is_show=True,
        commands=[
            Command(command="今日运势", description="查看今日运势"),
            Command(
                command="刷新今日运势", description="刷新所有人今日运势"
            ),
        ],
        superuser_help="""
        超级用户命令:
        - 刷新今日运势: 刷新所有人今日运势
        """,
    ).to_dict(),
)

fortune_cmd = on_alconna(
    Alconna("今日运势"),
    aliases={"/运势", "/今日运势", "运势"},
    priority=50,
    block=True,
)

refresh_fortune_cmd = on_alconna(
    Alconna("刷新今日运势"),
    permission=SUPERUSER,
    priority=50,
    block=True,
)


@fortune_cmd.handle()
async def _(session: Uninfo):
    """查看今日运势"""
    logger.info("查询今日运势", command="今日运势", session=session)
    await FortuneHandler.fortune(session)


@refresh_fortune_cmd.handle()
async def _(session: Uninfo):
    """刷新今日运势"""
    logger.info("刷新今日运势", command="刷新今日运势", session=session)
    await FortuneHandler.refresh_fortune(session)
