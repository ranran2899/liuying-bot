"""漂流瓶命令处理器"""
import re

from nonebot_plugin_alconna import UniMsg
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.config import Config
from liuying.models.bottle import BottleComment, BottleLike, BottleRecord
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils
from liuying.utils.platform import PlatformUtils

from .to_msg import BottleMessageBuilder

CONFIG_MODULE = "bottle"
BOTTLE_HELP_TEXT = """
    扔瓶子 [图片/文本]
    捡瓶子
    评论漂流瓶 [编号] [文本]
    点赞漂流瓶 [编号]
    查看漂流瓶 [编号]
    """.strip()


class BottleHandler:
    """漂流瓶命令处理器"""

    @classmethod
    async def view_bottle(
        cls, session: Uninfo, bottle_id: int
    ) -> None:
        """查看指定漂流瓶

        参数:
            session: 用户会话信息
            bottle_id: 漂流瓶ID
        """
        bottle = await BottleRecord.get_approved_by_id(bottle_id)
        if bottle is None:
            record = await BottleRecord.get_by_id(bottle_id)
            if record is None:
                await MessageUtils.build_message(
                    "漂流瓶不存在"
                ).finish(reply_to=True)
            match record.status:
                case 100:
                    msg = "漂流瓶已拒绝，无法查看!"
                case 0:
                    msg = "漂流瓶未审核"
                case _:
                    msg = "发生未知错误!"
            await MessageUtils.build_message(msg).finish(reply_to=True)

        messages = await BottleMessageBuilder.build_bottle_message(
            session, bottle
        )
        for message in messages[:-1]:
            await message.send()
        await messages[-1].finish(reply_to=True)

    @classmethod
    async def comment_bottle(
        cls, session: Uninfo, bottle_id: int, content: str
    ) -> None:
        """评论漂流瓶

        参数:
            session: 用户会话信息
            bottle_id: 漂流瓶ID
            content: 评论内容
        """
        if not content:
            await MessageUtils.build_message(
                "请输入评论内容"
            ).finish(reply_to=True)

        bottle = await BottleRecord.get_approved_by_id(bottle_id)
        if not bottle:
            await MessageUtils.build_message(
                "评论失败，漂流瓶不存在或未通过审核"
            ).finish(reply_to=True)

        await BottleComment.add_comment(
            bottle_id=bottle_id,
            content=content,
            user_id=session.user.id,
        )
        await MessageUtils.build_message(
            "评论成功! 等待审核后即可展示~"
        ).finish(reply_to=True)

    @classmethod
    async def like_bottle(
        cls, session: Uninfo, bottle_id: int
    ) -> None:
        """点赞漂流瓶

        参数:
            session: 用户会话信息
            bottle_id: 漂流瓶ID
        """
        if await BottleLike.has_liked(bottle_id, session.user.id):
            await MessageUtils.build_message(
                "你已经点赞过了~"
            ).finish(reply_to=True)

        bottle = await BottleRecord.get_by_id(bottle_id)
        if not bottle or bottle.status != 200:
            await MessageUtils.build_message(
                "点赞失败，漂流瓶不存在"
            ).finish(reply_to=True)

        await BottleLike.add_like(bottle_id, session.user.id)
        new_count = await BottleRecord.add_like(bottle_id)
        if new_count is None:
            await MessageUtils.build_message(
                "点赞失败，请稍后重试"
            ).finish(reply_to=True)

        await MessageUtils.build_message(
            f"点赞成功! 当前有{new_count}个赞~"
        ).finish(reply_to=True)

    @classmethod
    async def pick_bottle(cls, session: Uninfo) -> None:
        """捡漂流瓶

        参数:
            session: 用户会话信息
        """
        bottle = await BottleRecord.get_random_approved()
        if not bottle:
            await MessageUtils.build_message(
                "捞瓶子失败，没有漂流瓶~"
            ).finish(reply_to=True)

        messages = await BottleMessageBuilder.build_bottle_message(
            session, bottle
        )
        for message in messages[:-1]:
            await message.send()
        await messages[-1].finish(reply_to=True)

    @classmethod
    async def throw_bottle(
        cls,
        session: Uninfo,
        message: UniMsg,
        text_content: str,
    ) -> None:
        """丢瓶子

        参数:
            session: 用户会话信息
            message: 用户消息(用于提取图片)
            text_content: 命令后的纯文本内容
        """
        image_count = sum(1 for seg in message if seg.type == "image")
        has_image = image_count > 0

        if not text_content and not has_image:
            if Config.get_config(CONFIG_MODULE, "EMBEDDED_HELP", True):
                await MessageUtils.build_message(
                    f"您还没有写好瓶子的内容哦~\n"
                    f"漂流瓶食用方法: {BOTTLE_HELP_TEXT}"
                ).finish(reply_to=True)
            await MessageUtils.build_message(
                "您还没有写好瓶子的内容哦~"
            ).finish(reply_to=True)

        max_word = int(
            Config.get_config(CONFIG_MODULE, "MAX_BOTTLE_WORD", 1200)
            or 1200
        )
        if text_content and len(text_content) > max_word:
            await MessageUtils.build_message(
                f"丢瓶子失败啦，请不要超过{max_word}字符哦~"
            ).finish(reply_to=True)

        if text_content:
            max_lines = int(
                Config.get_config(CONFIG_MODULE, "MAX_BOTTLE_LINES", 9)
                or 9
            )
            newline_count = len(re.findall(r"[\r\n]+", text_content))
            if newline_count > max_lines:
                await MessageUtils.build_message(
                    f"丢瓶子失败啦，请不要超过{max_lines}行内容哦~"
                ).finish(reply_to=True)

        max_pic = int(
            Config.get_config(CONFIG_MODULE, "MAX_BOTTLE_PIC", 2) or 2
        )
        if image_count > max_pic:
            await MessageUtils.build_message(
                f"丢瓶子失败啦，请不要超过{max_pic}张图片哦~"
            ).finish(reply_to=True)

        platform = PlatformUtils.get_platform(session)
        record = await BottleRecord.create_bottle(
            content=text_content or None,
            user_id=session.user.id,
            platform=platform,
        )
        bottle_id = record.id

        if image_count > 0:
            try:
                await BottleMessageBuilder.save_message_images(
                    bottle_id, message
                )
            except Exception as e:
                logger.error(f"保存漂流瓶图片失败: {e}", "Bottle")

        await MessageUtils.build_message(
            f"丢瓶子成功! 瓶子ID是: {bottle_id}，"
            f"将在审核通过后出现在大海中~"
        ).finish(reply_to=True)
