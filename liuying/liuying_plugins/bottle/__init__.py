"""
漂流瓶插件

支持多适配器的漂流瓶功能，包含丢瓶子、捡瓶子、评论、点赞等
"""
import re

import nonebot
from nonebot import on_command
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, UniMsg, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.models.bottle import BottleComment, BottleLike, BottleRecord
from liuying.utils.log import logger
from liuying.utils.platform import PlatformUtils

from . import web_bottle as web_bottle  # noqa: F401,RUF100
from .config import Config
from .to_msg import build_bottle_message, save_message_images

config = nonebot.get_plugin_config(Config)

__plugin_meta__ = PluginMetadata(
    name="漂流瓶",
    description="基于NoneBot2的漂流瓶插件，支持多适配器，含Web审核功能",
    usage="""
    扔瓶子 [图片/文本]
    捡瓶子
    评论漂流瓶 [编号] [文本]
    点赞漂流瓶 [编号]
    查看漂流瓶 [编号]
    """,
    type="application",
    homepage="https://github.com/luosheng520qaq/nonebot-plugin-web-bottle",
    config=Config,
)

bottle_help_text = __plugin_meta__.usage

throw_cmd = on_command(
    "扔瓶子",
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

help_cmd = on_alconna(
    Alconna("漂流瓶"),
    aliases={"漂流瓶菜单"},
    priority=50,
    block=True,
)


@help_cmd.handle()
async def _():
    """漂流瓶帮助"""
    await help_cmd.finish(f"\n漂流瓶使用帮助{bottle_help_text}")


@view_bottle_cmd.handle()
async def _(session: Uninfo, bottle_id: int):
    """查看指定漂流瓶"""
    bottle = await BottleRecord.get_approved_by_id(bottle_id)
    if bottle is None:
        record = await BottleRecord.get_by_id(bottle_id)
        if record is None:
            await view_bottle_cmd.finish("漂流瓶不存在")
        match record.status:
            case 100:
                await view_bottle_cmd.finish("漂流瓶已拒绝，无法查看!")
            case 0:
                await view_bottle_cmd.finish("漂流瓶未审核")
            case _:
                await view_bottle_cmd.finish("发生未知错误!")

    messages = await build_bottle_message(session, bottle)
    for message in messages:
        await view_bottle_cmd.send(message)
    await view_bottle_cmd.finish()


@comment_cmd.handle()
async def _(session: Uninfo, bottle_id: int, content: str):
    """评论漂流瓶"""
    if not content:
        await comment_cmd.finish("请输入评论内容")

    bottle = await BottleRecord.get_approved_by_id(bottle_id)
    if not bottle:
        await comment_cmd.finish("评论失败，漂流瓶不存在或未通过审核")

    await BottleComment.add_comment(
        bottle_id=bottle_id,
        content=content,
        user_id=session.user.id,
    )
    await comment_cmd.finish("评论成功! 等待审核后即可展示~")


@like_bottle_cmd.handle()
async def _(session: Uninfo, bottle_id: int):
    """点赞漂流瓶"""
    if await BottleLike.has_liked(bottle_id, session.user.id):
        await like_bottle_cmd.finish("你已经点赞过了~")

    bottle = await BottleRecord.get_by_id(bottle_id)
    if not bottle or bottle.status != 200:
        await like_bottle_cmd.finish("点赞失败，漂流瓶不存在")

    await BottleLike.add_like(bottle_id, session.user.id)
    new_count = await BottleRecord.add_like(bottle_id)

    if new_count is None:
        await like_bottle_cmd.finish("点赞失败，请稍后重试")

    await like_bottle_cmd.finish(f"点赞成功! 当前有{new_count}个赞~")


@get_bottle_cmd.handle()
async def _(session: Uninfo):
    """捡漂流瓶"""
    bottle = await BottleRecord.get_random_approved()
    if not bottle:
        await get_bottle_cmd.finish("捞瓶子失败，没有漂流瓶~")

    messages = await build_bottle_message(session, bottle)
    for message in messages:
        await get_bottle_cmd.send(message)
    await get_bottle_cmd.finish()


@throw_cmd.handle()
async def _(session: Uninfo, message: UniMsg):
    """丢瓶子"""
    text_content = "".join(
        str(seg) for seg in message if seg.type == "text"
    ).strip()

    if not text_content and not any(seg.type == "image" for seg in message):
        if config.embedded_help:
            await throw_cmd.finish(
                f"您还没有写好瓶子的内容哦~\n"
                f"漂流瓶食用方法: {bottle_help_text}"
            )
        await throw_cmd.finish("您还没有写好瓶子的内容哦~")

    if text_content and len(text_content) > config.max_bottle_word:
        await throw_cmd.finish(
            f"丢瓶子失败啦，请不要超过{config.max_bottle_word}字符哦~"
        )

    newline_pattern = r"[\r\n]+"
    newline_count = len(re.findall(newline_pattern, text_content))
    if text_content and newline_count > config.max_bottle_lines:
        await throw_cmd.finish(
            f"丢瓶子失败啦，请不要超过{config.max_bottle_lines}行内容哦~"
        )

    image_count = sum(1 for seg in message if seg.type == "image")
    if image_count > config.max_bottle_pic:
        await throw_cmd.finish(
            f"丢瓶子失败啦，请不要超过{config.max_bottle_pic}张图片哦~"
        )

    platform = PlatformUtils.get_platform(session)
    record = await BottleRecord.create_bottle(
        content=text_content or None,
        user_id=session.user.id,
        group_id=session.scene.id if session.scene.is_group else None,
        platform=platform,
    )
    bottle_id = record.id

    if image_count > 0:
        try:
            await save_message_images(bottle_id, message)
        except Exception as e:
            logger.error(f"保存漂流瓶图片失败: {e}", "Bottle")

    await throw_cmd.finish(
        f"丢瓶子成功! 瓶子ID是: {bottle_id}，将在审核通过后出现在大海中~"
    )
