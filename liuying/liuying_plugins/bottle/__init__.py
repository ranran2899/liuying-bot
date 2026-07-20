"""
漂流瓶插件

支持多适配器的漂流瓶功能，包含丢瓶子、捡瓶子、评论、点赞等
"""
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

from liuying.configs.utils import (
    Command,
    PluginExtraData,
    RegisterConfig,
)
from liuying.utils.enum import PluginType
from liuying.utils.log import logger

from .handler import BottleHandler

__plugin_meta__ = PluginMetadata(
    name="漂流瓶",
    description="基于NoneBot2的漂流瓶插件，支持多适配器，含Web审核功能",
    usage="""
    扔瓶子 [图片/文本]
    捡瓶子
    评论漂流瓶 [编号] [文本]
    点赞漂流瓶 [编号]
    查看漂流瓶 [编号]
    """.strip(),
    type="application",
    homepage="https://github.com/luosheng520qaq/nonebot-plugin-web-bottle",
    extra=PluginExtraData(
        author="liuying",
        version="0.3",
        plugin_type=PluginType.NORMAL,
        menu_type="娱乐",
        is_show=True,
        commands=[
            Command(command="扔瓶子", description="扔出一个漂流瓶"),
            Command(command="捡瓶子", description="随机捡一个漂流瓶"),
            Command(command="查看漂流瓶", description="查看指定漂流瓶"),
            Command(command="评论漂流瓶", description="评论指定漂流瓶"),
            Command(command="点赞漂流瓶", description="为指定漂流瓶点赞"),
        ],
        configs=[
            RegisterConfig(
                key="MAX_BOTTLE_PIC",
                value=2,
                help="最大漂流瓶图片数量",
                default_value=2,
                type=int,
            ),
            RegisterConfig(
                key="MAX_BOTTLE_LINES",
                value=9,
                help="最大漂流瓶文本行数",
                default_value=9,
                type=int,
            ),
            RegisterConfig(
                key="MAX_BOTTLE_WORD",
                value=1200,
                help="最大漂流瓶文本字符数",
                default_value=1200,
                type=int,
            ),
            RegisterConfig(
                key="EMBEDDED_HELP",
                value=True,
                help="是否嵌入帮助信息",
                default_value=True,
                type=bool,
            ),
            RegisterConfig(
                key="DEFAULT_NICKNAME",
                value="未知用户",
                help="UID获取失败时的默认昵称",
                default_value="未知用户",
                type=str,
            ),
            RegisterConfig(
                key="BOTTLE_MSG_SPLIT",
                value=True,
                help="是否将漂流瓶消息与评论拆分发送",
                default_value=True,
                type=bool,
            ),
            RegisterConfig(
                key="MAX_BOTTLE_COMMENTS",
                value=3,
                help="单条漂流瓶展示的最大评论数量",
                default_value=3,
                type=int,
            ),
            RegisterConfig(
                key="BOTTLE_MSG_UID",
                value=True,
                help="是否在消息中展示发送者UID",
                default_value=True,
                type=bool,
            ),
        ],
    ).to_dict(),
)

throw_cmd = on_alconna(
    Alconna("扔瓶子", Args["content?", str], CommandMeta(strict=False)),
    aliases={"丢瓶子"},
    priority=50,
    block=True,
)

get_bottle_cmd = on_alconna(
    Alconna("捡瓶子"),
    aliases={"捡漂流瓶"},
    priority=50,
    block=True,
)

like_bottle_cmd = on_alconna(
    Alconna("点赞漂流瓶", Args["bottle_id", int]),
    priority=50,
    block=True,
)

comment_cmd = on_alconna(
    Alconna("评论漂流瓶", Args["bottle_id", int]["content", str]),
    priority=50,
    block=True,
)

view_bottle_cmd = on_alconna(
    Alconna("查看漂流瓶", Args["bottle_id", int]),
    priority=50,
    block=True,
)

@view_bottle_cmd.handle()
async def _(session: Uninfo, bottle_id: int):
    """查看指定漂流瓶"""
    logger.info(
        f"查看漂流瓶 id={bottle_id}",
        command="查看漂流瓶",
        session=session,
    )
    await BottleHandler.view_bottle(session, bottle_id)


@comment_cmd.handle()
async def _(session: Uninfo, bottle_id: int, content: str):
    """评论漂流瓶"""
    logger.info(
        f"评论漂流瓶 id={bottle_id}",
        command="评论漂流瓶",
        session=session,
    )
    await BottleHandler.comment_bottle(session, bottle_id, content)


@like_bottle_cmd.handle()
async def _(session: Uninfo, bottle_id: int):
    """点赞漂流瓶"""
    logger.info(
        f"点赞漂流瓶 id={bottle_id}",
        command="点赞漂流瓶",
        session=session,
    )
    await BottleHandler.like_bottle(session, bottle_id)


@get_bottle_cmd.handle()
async def _(session: Uninfo):
    """捡漂流瓶"""
    logger.info("捡漂流瓶", command="捡瓶子", session=session)
    await BottleHandler.pick_bottle(session)


@throw_cmd.handle()
async def _(
    session: Uninfo,
    message: UniMsg,
    content: Match[str],
):
    """丢瓶子"""
    logger.info("丢漂流瓶", command="扔瓶子", session=session)
    text_content = content.result.strip() if content.available else ""
    await BottleHandler.throw_bottle(session, message, text_content)
