import base64
from io import BytesIO
from pathlib import Path
import random
from typing import ClassVar

import nonebot
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot_plugin_alconna import (
    At,
    AtAll,
    Audio,
    Button,
    CustomNode,
    Emoji,
    File,
    Hyper,
    Image,
    Keyboard,
    Other,
    Reference,
    Reply,
    Text,
    UniMessage,
    Video,
    Voice,
)
from pydantic import BaseModel

from liuying.configs.config import BotConfig
from liuying.services.log import logger
from liuying.utils.image import BuildImage

MESSAGE_TYPE = (
    str
    | int
    | float
    | Path
    | bytes
    | BytesIO
    | BuildImage
    | At
    | AtAll
    | Audio
    | Button
    | CustomNode
    | Emoji
    | File
    | Hyper
    | Image
    | Keyboard
    | Other
    | Reference
    | Reply
    | Text
    | Video
    | Voice
)


class Config(BaseModel):
    image_to_bytes: bool = False
    """是否将图片转换为bytes发送"""


class MessageUtils:
    FAILURE_MESSAGES: ClassVar[list[str]] = [
        "出了点小问题，待会再试试吧~ (´・ω・`)",
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
        config = nonebot.get_plugin_config(Config)
        match msg:
            case Path():
                if msg.exists():
                    if config.image_to_bytes:
                        logger.debug("图片转为bytes发送", "MessageUtils")
                        return Image(raw=BuildImage.open(msg).pic2bytes())
                    return Image(path=msg)
                logger.warning(f"图片路径不存在: {msg}")
            case bytes():
                return Image(raw=msg)
            case BytesIO():
                return Image(raw=msg)
            case BuildImage():
                return Image(raw=msg.pic2bytes())
        return None

    @classmethod
    def __build_message(
        cls, msg_list: list[MESSAGE_TYPE], format_args: dict | None = None
    ) -> list:
        """构造消息

        参数:
            msg_list: 消息列表
            format_args: 用于格式化字符串的参数字典.

        返回:
            list: 构造完成的消息列表
        """
        message_list = []
        for msg in msg_list:
            match msg:
                case str():
                    if msg.startswith("base64://"):
                        message_list.append(
                            Image(raw=BytesIO(base64.b64decode(msg[9:])))
                        )
                    else:
                        formatted_msg = msg
                        if format_args:
                            try:
                                formatted_msg = msg.format_map(format_args)
                            except (KeyError, IndexError) as e:
                                logger.debug(
                                    f"格式化字符串 '{msg}' 失败 ({e})，将使用原始文本。"
                                )
                        message_list.append(Text(formatted_msg))
                case int() | float():
                    message_list.append(Text(str(msg)))
                case Path() | bytes() | BytesIO() | BuildImage():
                    if image := cls._convert_media(msg):
                        message_list.append(image)
                case _:
                    message_list.append(msg)
        return message_list

    @classmethod
    def build_message(
        cls,
        msg_list: MESSAGE_TYPE | list[MESSAGE_TYPE | list[MESSAGE_TYPE]],
        format_args: dict | None = None,
    ) -> UniMessage:
        """构造消息

        参数:
            msg_list: 消息列表
            format_args: 用于格式化字符串的参数字典.

        返回:
            UniMessage: 构造完成的消息列表
        """
        if not isinstance(msg_list, list):
            msg_list = [msg_list]
        items = [
            item
            for m in msg_list
            for item in cls.__build_message(
                m if isinstance(m, list) else [m], format_args
            )
        ]
        return UniMessage(items)

    @staticmethod
    def _process_forward_node(msg: MESSAGE_TYPE) -> MESSAGE_TYPE:
        """处理转发消息节点中的媒体类型

        参数:
            msg: 消息元素

        返回:
            MESSAGE_TYPE: 处理后的消息元素
        """
        match msg:
            case Path():
                return Image(raw=BuildImage.open(msg).pic2bytes())
            case BuildImage():
                return Image(raw=msg.pic2bytes())
            case _:
                return msg

    @classmethod
    def alc_forward_msg(
        cls,
        msg_list: list,
        uin: str,
        name: str,
    ) -> UniMessage:
        """生成自定义合并消息

        参数:
            msg_list: 消息列表
            uin: 发送者 QQ
            name: 自定义名称

        返回:
            UniMessage: 转发消息
        """
        nodes = [
            CustomNode(
                uid=uin,
                name=name,
                content=UniMessage(
                    [cls._process_forward_node(m) for m in msg]
                    if isinstance(msg := _msg, list)
                    else _msg
                ),
            )
            for _msg in msg_list
        ]
        return UniMessage(Reference(nodes=nodes))

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
        if buttons and isinstance(buttons[0], list):
            for row in buttons:
                message.keyboard(*row)
        else:
            message.keyboard(*buttons)
        return message

    @classmethod
    def custom_forward_msg(
        cls,
        msg_list: list[str | Message],
        uin: str,
        name: str = f"这里是{BotConfig.self_nickname}",
    ) -> list[dict]:
        """生成自定义合并消息

        参数:
            msg_list: 消息列表
            uin: 发送者 QQ
            name: 自定义名称

        返回:
            list[dict]: 转发消息
        """
        return [
            {
                "type": "node",
                "data": {"name": name, "uin": uin, "content": msg},
            }
            for msg in msg_list
        ]

    @classmethod
    def template2forward(cls, msg_list: list[UniMessage], uni: str) -> list[dict]:
        """模板转转发消息

        参数:
            msg_list: 消息列表
            uni: 发送者qq

        返回:
            list[dict]: 转发消息
        """

        def convert(item: UniMessage | Image) -> str:
            match item:
                case UniMessage() | list():
                    parts = []
                    for r in item:
                        match r:
                            case Text():
                                parts.append(str(r))
                            case Image() if (v := r.url or r.path or r.raw):
                                parts.append(MessageSegment.image(v))
                    return "".join(parts)
                case Image() if (v := item.url or item.path):
                    return MessageSegment.image(v)
                case _:
                    return str(item)

        return cls.custom_forward_msg([convert(m) for m in msg_list], uni)

    @classmethod
    def template2alc(cls, msg_list: list[str | MessageSegment]) -> list:
        """模板转alc

        参数:
            msg_list: 消息列表

        返回:
            list: alc模板
        """
        result = []
        for msg in msg_list:
            match msg:
                case str():
                    result.append(Text(msg))
                case MessageSegment(type="at", data={"qq": qq}):
                    result.append(
                        AtAll() if qq == "0" else At(flag="user", target=qq)
                    )
                case MessageSegment(type="image", data=data):
                    result.append(Image(url=data.get("file") or data.get("url")))
                case MessageSegment(type="text", data={"text": text}) if text:
                    result.append(Text(text))
        return result
