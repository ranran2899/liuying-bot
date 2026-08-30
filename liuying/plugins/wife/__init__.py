"""每日wife插件 - 随机抽取二次元老婆"""

from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    CommandMeta,
    Match,
    UniMsg,
    on_alconna,
)
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import Command, PluginExtraData, RegisterConfig
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

from ._data_source import WifeManage

__plugin_meta__ = PluginMetadata(
    name="每日wife",
    description="每日随机二次元老婆",
    usage="""
    抽wife / 抽老婆 / 随机wife / 随机老婆 / 今日wife / 今日老婆
    查找wife [名字] (超级用户)
    添加wife [名字] (回复图片消息) (超级用户)
    删除wife [名字] (超级用户)
    清空wife库 (超级用户)
    重置wife库 (超级用户)
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.2",
        plugin_type=PluginType.NORMAL,
        menu_type="娱乐",
        is_show=True,
        commands=[
            Command(command="抽wife", description="随机抽取一个wife"),
            Command(command="查找wife", params=["名字"], description="查找指定wife"),
            Command(command="添加wife", params=["名字"], description="添加wife到库中"),
            Command(command="删除wife", params=["名字"], description="删除指定wife"),
            Command(command="清空wife库", description="清空所有wife"),
            Command(command="重置wife库", description="重置wife库到初始状态"),
        ],
        configs=[
            RegisterConfig(
                key="ENABLE_GOLD",
                value=20,
                help="获得的金币奖励",
                default_value=20,
                type=int,
            ),
        ],
        superuser_help="""
        超级用户命令:
        - 查找wife [名字]: 查找指定wife
        - 添加wife [名字]: 回复图片消息添加wife
        - 删除wife [名字]: 删除指定wife
        - 清空wife库: 清空所有wife
        - 重置wife库: 重置到初始状态
        """,
    ).to_dict(),
)

draw_wife_cmd = on_alconna(
    Alconna("抽wife"),
    aliases={"抽老婆", "随机wife", "随机老婆", "今日wife", "今日老婆"},
    priority=50,
    block=True,
)

search_wife_cmd = on_alconna(
    Alconna("查找wife", Args["wife_name", str]),
    aliases={"查找老婆"},
    permission=SUPERUSER,
    priority=50,
    block=True,
)

add_wife_cmd = on_alconna(
    Alconna("添加wife", Args["wife_name?", str], CommandMeta(strict=False)),
    aliases={"添加老婆"},
    permission=SUPERUSER,
    priority=50,
    block=True,
)

del_wife_cmd = on_alconna(
    Alconna("删除wife", Args["wife_name", str]),
    aliases={"删除老婆"},
    permission=SUPERUSER,
    priority=50,
    block=True,
)

clear_wife_cmd = on_alconna(
    Alconna("清空wife库"),
    aliases={"清空老婆库"},
    permission=SUPERUSER,
    priority=50,
    block=True,
)

reset_wife_cmd = on_alconna(
    Alconna("重置wife库"),
    aliases={"重置老婆库"},
    permission=SUPERUSER,
    priority=50,
    block=True,
)


@draw_wife_cmd.handle()
async def _(session: Uninfo):
    """抽wife"""
    logger.info("用户抽wife请求", command="抽wife", session=session)
    result = await WifeManage.draw_wife(session.user.id)
    await MessageUtils.build_message(result).finish(reply_to=True)


@search_wife_cmd.handle()
async def _(session: Uninfo, wife_name: str):
    """查找wife"""
    logger.info(f"查找wife: {wife_name}", command="查找wife", session=session)
    await MessageUtils.build_message(await WifeManage.search_wife(wife_name)).finish()


@add_wife_cmd.handle()
async def _(session: Uninfo, message: UniMsg, wife_name: Match[str]):
    """添加wife"""
    name = wife_name.result.strip() if wife_name.available else ""
    if not name:
        await MessageUtils.build_message("名字呢?").finish()

    urls = [
        url
        for seg in message
        if seg.type == "image" and (url := seg.data.get("url") or seg.data.get("file"))
    ]
    if not urls:
        await MessageUtils.build_message("图呢?").finish()

    logger.info(f"添加wife: {name}", command="添加wife", session=session)
    await MessageUtils.build_message(await WifeManage.add_wife(name, urls)).finish()


@del_wife_cmd.handle()
async def _(session: Uninfo, wife_name: str):
    """删除wife"""
    logger.info(f"删除wife: {wife_name}", command="删除wife", session=session)
    await MessageUtils.build_message(await WifeManage.del_wife(wife_name)).finish()


@clear_wife_cmd.handle()
async def _(session: Uninfo):
    """清空wife库"""
    logger.info("清空wife库请求", command="清空wife库", session=session)
    await MessageUtils.build_message(await WifeManage.clear_wife()).finish()


@reset_wife_cmd.handle()
async def _(session: Uninfo):
    """重置wife库"""
    logger.info("重置wife库请求", command="重置wife库", session=session)
    await MessageUtils.build_message(await WifeManage.reset_wife()).finish()
