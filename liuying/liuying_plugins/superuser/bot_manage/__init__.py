from typing import cast

import nonebot
from nonebot.adapters import Bot
from nonebot.plugin import PluginMetadata

from liuying.configs.utils import PluginExtraData
from liuying.models._bot import BotConsole
from liuying.models.plugin_info import PluginInfo
from liuying.models.task_info import TaskInfo
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.platform import PlatformUtils

driver = nonebot.get_driver()


__plugin_meta__ = PluginMetadata(
    name="Bot管理",
    description="指定bot对象的功能/被动开关和状态",
    usage="""
    指令:
        bot被动状态                 : bot的被动技能状态
        bot开启/关闭被动[被动名称]    : 被动技能开关
        bot开启/关闭所有被动          : 所有被动技能开关
        bot插件列表: bot插件列表状态  : bot插件列表
        bot开启/关闭所有插件          : 所有插件开关
        bot开启/关闭插件[插件名称]    : 插件开关
        bot休眠                    : bot休眠，屏蔽所有消息
        bot醒来                    : bot醒来
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.1",
        plugin_type=PluginType.SUPERUSER,
    ).to_dict(),
)

from . import bot_switch, full_function, plugin, task  # noqa: F401


def _filter_blocked_items(items_list: list[str], block_list: list[str]) -> list[str]:
    """过滤被block的项目"""
    return [item for item in items_list if item not in block_list]


@driver.on_bot_connect
async def init_bot_console(bot: Bot):
    """初始化Bot管理

    参数:
        bot: Bot
    """
    plugin_list = [
        p.module
        for p in await PluginInfo.filter()
        .where_in(
            "plugin_type", [PluginType.NORMAL, PluginType.DEPENDANT, PluginType.ADMIN]
        )
        .all()
    ]
    task_list = cast(
        list[str], await TaskInfo.filter(status=True).values_list("module", flat=True)
    )
    platform = PlatformUtils.get_platform(bot)
    bot_data, created = await BotConsole.get_or_create(
        bot_id=bot.self_id, platform=platform
    )

    if not created:
        task_list = _filter_blocked_items(
            task_list, await bot_data.get_tasks(bot.self_id, False)
        )
        plugin_list = _filter_blocked_items(
            plugin_list, await bot_data.get_plugins(bot.self_id, False)
        )

    bot_data.available_plugins = BotConsole.convert_module_format(plugin_list)
    bot_data.available_tasks = BotConsole.convert_module_format(task_list)
    await bot_data.save()
    logger.info("初始化Bot管理完成...")
