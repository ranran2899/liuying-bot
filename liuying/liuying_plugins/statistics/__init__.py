from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Arparma,
    Match,
    Option,
    on_alconna,
    store_true,
)
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import Command, PluginExtraData
from liuying.utils.enum import PluginType
from liuying.utils.message import MessageUtils

from ._data_source import StatisticsManage

__plugin_meta__ = PluginMetadata(
    name="功能调用统计",
    description="功能调用统计可视化",
    usage="""
    usage：
    功能调用统计可视化
    指令：
        功能调用统计
        日功能调用统计
        周功能调用统计
        月功能调用统计
        我的功能调用统计   : 当前群我的统计
        我的功能调用统计 -g: 我的全局统计
        我的日功能调用统计
        我的周功能调用统计
        我的月功能调用统计
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.1",
        plugin_type=PluginType.NORMAL,
        menu_type="功能",
        aliases={"功能调用统计"},
        superuser_help="""
        "全局功能调用统计",
        "全局日功能调用统计",
        "全局周功能调用统计",
        "全局月功能调用统计",
        """.strip(),
        commands=[
            Command(command="功能调用统计"),
            Command(command="日功能调用统计"),
            Command(command="周功能调用统计"),
            Command(command="我的功能调用统计"),
            Command(command="我的日功能调用统计"),
            Command(command="我的周功能调用统计"),
            Command(command="我的月功能调用统计"),
        ],
    ).to_dict(),
)


SHORTCUTS = [
    ("日功能调用统计(?P<name>.*)", ["{name}", "-t", "day"]),
    ("周功能调用统计(?P<name>.*)", ["{name}", "-t", "week"]),
    ("月功能调用统计(?P<name>.*)", ["{name}", "-t", "month"]),
    ("全局功能调用统计(?P<name>.*)", ["{name}", "-g"]),
    ("全局日功能调用统计(?P<name>.*)", ["{name}", "-t", "day", "-g"]),
    ("全局周功能调用统计(?P<name>.*)", ["{name}", "-t", "week", "-g"]),
    ("全局月功能调用统计(?P<name>.*)", ["{name}", "-t", "month", "-g"]),
    ("我的功能调用统计(?P<name>.*)", ["{name}", "-my"]),
    ("我的日功能调用统计(?P<name>.*)", ["{name}", "-t", "day", "-my"]),
    ("我的周功能调用统计(?P<name>.*)", ["{name}", "-t", "week", "-my"]),
    ("我的月功能调用统计(?P<name>.*)", ["{name}", "-t", "month", "-my"]),
]

_matcher = on_alconna(
    Alconna(
        "功能调用统计",
        Args["name?", str],
        Option("-g|--global", action=store_true, help_text="全局统计"),
        Option("-my", action=store_true, help_text="我的"),
        Option("-t|--type", Args["search_type", ["day", "week", "month"]]),
    ),
    priority=5,
    block=True,
)

for shortcut, arguments in SHORTCUTS:
    _matcher.shortcut(
        shortcut, command="功能调用统计", arguments=arguments, prefix=True
    )


@_matcher.handle()
async def _(
    uninfo: Uninfo,
    arparma: Arparma,
    name: Match[str],
    search_type: Match[str],
):
    """处理功能调用统计命令。"""
    plugin_name = name.result if name.available else None
    st = search_type.result if search_type.available else None

    uid = uninfo.user.id
    group_id = (
        uninfo.group.parent.id if uninfo.group.parent else uninfo.group.id
    ) if uninfo.group else None

    is_my = arparma.find("my")
    is_global = arparma.find("global")

    if not is_my and group_id:
        uid = None

    if uid and is_global:
        group_id = None

    result = await StatisticsManage.get_statistics(
        plugin_name, is_global, st, uid, group_id
    )

    match result:
        case None:
            await MessageUtils.build_message("获取数据失败...").send()
        case str():
            await MessageUtils.build_message(result).finish(reply_to=True)
        case _:
            await MessageUtils.build_message(result).send()

