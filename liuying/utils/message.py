"""消息工具类

基于 nonebot_plugin_alconna 的 UniMessage 构建多平台消息，
不包含任何平台特定逻辑，由 UniMessage 负责各适配器的序列化。
"""

import base64
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import random
from typing import ClassVar

import nonebot
from nonebot_plugin_alconna import Button, Image, Segment, Text, UniMessage
from pydantic import BaseModel

from liuying.services.log import logger
from liuying.utils.image import BuildImage

type MESSAGE_TYPE = str | int | float | Path | bytes | BytesIO | BuildImage | Segment


class Config(BaseModel):
    image_to_bytes: bool = False
    """是否将图片转换为bytes发送"""


@lru_cache(maxsize=1)
def _get_media_config() -> Config:
    """获取媒体发送配置

    进程内缓存，避免每次发送图片都重复解析 pydantic 配置。

    返回:
        Config: 媒体发送配置
    """
    return nonebot.get_plugin_config(Config)


class MessageUtils:
    FAILURE_MESSAGES: ClassVar[list[str]] = [
        "出了点小问题，待会再试试吧~ ",
        "哎呀，失败了呢 QAQ",
    ]

    @classmethod
    def get_failure_message(cls) -> str:
        """获取随机失败提示消息

        返回:
            str: 随机的可爱失败提示消息
        """
        return random.choice(cls.FAILURE_MESSAGES)

    @classmethod
    def build_failure_message(cls) -> UniMessage:
        """构造随机失败提示消息

        返回:
            UniMessage: 构造完成的失败提示消息
        """
        return cls.build_message(cls.get_failure_message())

    @staticmethod
    def _convert_media(msg: Path | bytes | BytesIO | BuildImage) -> Image | None:
        """转换媒体类型为 Image 对象

        参数:
            msg: 媒体对象

        返回:
            Image | None: 转换后的 Image 对象，路径不存在时返回 None
        """
        match msg:
            case Path() if msg.exists():
                if _get_media_config().image_to_bytes:
                    logger.debug("图片转为bytes发送", "MessageUtils")
                    return Image(raw=BuildImage.open(msg).pic2bytes())
                return Image(path=msg)
            case Path():
                logger.warning(f"图片路径不存在: {msg}")
            case bytes() | BytesIO():
                return Image(raw=msg)
            case BuildImage():
                return Image(raw=msg.pic2bytes())
        return None

    @classmethod
    def __build_single(
        cls, msg: MESSAGE_TYPE, format_args: dict | None
    ) -> list:
        """构造单个消息元素

        参数:
            msg: 消息元素
            format_args: 用于格式化字符串的参数字典

        返回:
            list: 构造完成的消息元素列表
        """
        match msg:
            case str() if msg.startswith("base64://"):
                return [Image(raw=BytesIO(base64.b64decode(msg[9:])))]
            case str():
                text = msg
                if format_args:
                    try:
                        text = msg.format_map(format_args)
                    except (KeyError, IndexError) as e:
                        logger.debug(
                            f"格式化字符串 '{msg}' 失败 ({e})，将使用原始文本。"
                        )
                return [Text(text)]
            case int() | float():
                return [Text(str(msg))]
            case Path() | bytes() | BytesIO() | BuildImage():
                if image := cls._convert_media(msg):
                    return [image]
                return []
            case _:
                return [msg]

    @classmethod
    def build_message(
        cls,
        msg_list: MESSAGE_TYPE | list[MESSAGE_TYPE | list[MESSAGE_TYPE]],
        format_args: dict | None = None,
    ) -> UniMessage:
        """构造消息

        参数:
            msg_list: 消息列表
            format_args: 用于格式化字符串的参数字典

        返回:
            UniMessage: 构造完成的消息列表
        """
        if not isinstance(msg_list, list):
            msg_list = [msg_list]
        items = [
            item
            for m in msg_list
            for sub in (m if isinstance(m, list) else [m])
            for item in cls.__build_single(sub, format_args)
        ]
        return UniMessage(items)

    @classmethod
    def build_markdown_message(
        cls,
        content: str,
        buttons: list[Button] | list[list[Button]] | None = None,
    ) -> UniMessage:
        """快速构建qq的 Markdown + 按钮格式消息

        参数:
            content: Markdown 内容字符串
            buttons: 可选的按钮列表，支持两种格式：
                - list[Button]: 所有按钮在同一行
                - list[list[Button]]: 每个子列表为一行按钮，支持自定义换行布局

        返回:
            UniMessage: 构造完成的 Markdown 消息

        示例:
            所有按钮同一行::

                buttons = [btn1, btn2, btn3]

            自定义换行布局，第一行2个按钮，第二行4个按钮::

                buttons = [
                    [btn1, btn2],
                    [btn3, btn4, btn5, btn6],
                ]
        """
        message = UniMessage([Text(content).mark(0, len(content), "markdown")])
        if not buttons:
            return message
        if isinstance(buttons[0], list):
            for row in buttons:
                message.keyboard(*row)
        else:
            message.keyboard(*buttons)
        return message
