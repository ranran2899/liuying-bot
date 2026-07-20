"""
漂流瓶消息构建模块

支持多适配器消息发送，包含普通消息和QQ Markdown消息两种模式
"""
import asyncio
from datetime import datetime
import io

import httpx
from nonebot_plugin_alconna import Button, UniMsg
from nonebot_plugin_uninfo import Uninfo
from PIL import Image as PILImage

from liuying.configs.config import Config
from liuying.models._user.user_info import UserInfo
from liuying.models.bottle import BottleComment, BottleImage, BottleRecord
from liuying.utils.bed_layout import BedLayout
from liuying.utils.enum import StorageType
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils
from liuying.utils.platform import PlatformUtils

CONFIG_MODULE = "bottle"
BOTTLE_IMAGE_DIR = "bottle"
MAX_RETRIES = 3
RETRY_DELAY = 1.0
WEBP_QUALITY = 80
DOWNLOAD_TIMEOUT = 30
IMAGE_DOWNLOAD_CONCURRENCY = 2


class BottleMessageBuilder:
    """漂流瓶消息构建器

    根据适配器类型构建普通消息或QQ Markdown消息，
    统一展示发送者UID而非原始user_id，保护隐私同时保持身份可识别
    """

    @staticmethod
    def _convert_to_webp(image_data: bytes) -> tuple[bytes, int, int]:
        """将图片数据转换为WEBP格式

        参数:
            image_data: 原始图片二进制数据

        返回:
            tuple[bytes, int, int]: (webp数据, 宽度, 高度)
        """
        image = PILImage.open(io.BytesIO(image_data))
        width, height = image.size
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="WEBP", quality=WEBP_QUALITY)
        return buffer.getvalue(), width, height

    @staticmethod
    async def _download_image_segment(seg) -> bytes | None:
        """下载消息段中的图片数据

        参数:
            seg: 消息段

        返回:
            bytes | None: 图片二进制数据，失败返回None
        """
        url = seg.data.get("url")
        if not url:
            raw = seg.data.get("raw")
            if isinstance(raw, bytes):
                return raw
            if hasattr(raw, "read"):
                return raw.read()
            return None

        try:
            async with httpx.AsyncClient(
                timeout=DOWNLOAD_TIMEOUT, follow_redirects=True
            ) as client:
                response = await client.get(
                    url, headers={"User-Agent": "Mozilla/5.0"}
                )
                if response.status_code == 200:
                    return response.content
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            logger.warning(f"下载图片失败: {e}", "BottleMsg")
        return None

    @classmethod
    async def _upload_persistent_image(
        cls, bottle_id: int, image_data: bytes, image_index: int
    ) -> dict[str, str] | None:
        """上传漂流瓶图片到本地数据库存储（持久化，不删除）

        参数:
            bottle_id: 漂流瓶ID
            image_data: 图片二进制数据
            image_index: 图片序号

        返回:
            dict | None: 包含url/width/height/filename的字典，失败返回None
        """
        filename = f"{BOTTLE_IMAGE_DIR}/{bottle_id}/{image_index}.webp"
        for attempt in range(MAX_RETRIES):
            try:
                url, _, filename_result = await BedLayout.upload(
                    file_data=image_data,
                    filename=filename,
                    extension=".webp",
                    content_type="image/webp",
                    storage_type=StorageType.LOCAL,
                )
                if not url:
                    logger.warning(
                        f"上传漂流瓶图片失败"
                        f"(尝试 {attempt + 1}/{MAX_RETRIES}): URL为空",
                        "BottleMsg",
                    )
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_DELAY)
                        continue
                    return None

                _, width, height = cls._convert_to_webp(image_data)
                await BottleImage.create_image(
                    bottle_id=bottle_id,
                    filename=filename_result,
                    image_index=image_index,
                    width=width,
                    height=height,
                )
                logger.info(
                    f"上传漂流瓶图片成功: "
                    f"bottle_id={bottle_id}, index={image_index}",
                    "BottleMsg",
                )
                return {
                    "url": url,
                    "width": str(width),
                    "height": str(height),
                    "filename": filename_result,
                }
            except Exception as e:
                logger.error(
                    f"上传漂流瓶图片异常"
                    f"(尝试 {attempt + 1}/{MAX_RETRIES}): {e}",
                    "BottleMsg",
                )
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    return None
        return None

    @classmethod
    async def save_message_images(
        cls, bottle_id: int, message: UniMsg
    ) -> list[dict[str, str]]:
        """保存消息中的图片到本地数据库存储（持久化）

        参数:
            bottle_id: 漂流瓶ID
            message: 消息对象

        返回:
            list[dict]: 上传成功的图片信息列表
        """
        image_segments = [
            seg for seg in message if seg.type == "image"
        ][: int(Config.get_config(CONFIG_MODULE, "MAX_BOTTLE_PIC", 2) or 2)]
        if not image_segments:
            return []

        semaphore = asyncio.Semaphore(IMAGE_DOWNLOAD_CONCURRENCY)

        async def _process_image(
            index: int, seg
        ) -> dict[str, str] | None:
            """并发处理单张图片下载与上传"""
            async with semaphore:
                try:
                    image_data = await cls._download_image_segment(seg)
                    if not image_data:
                        return None
                    webp_data, _, _ = cls._convert_to_webp(image_data)
                    return await cls._upload_persistent_image(
                        bottle_id, webp_data, index
                    )
                except Exception as e:
                    logger.error(
                        f"处理图片 {index} 失败: {e}", "BottleMsg"
                    )
                    return None

        results = await asyncio.gather(
            *(
                _process_image(i, seg)
                for i, seg in enumerate(image_segments)
            )
        )
        return [r for r in results if r]

    @staticmethod
    async def get_bottle_image_urls(
        bottle_id: int,
    ) -> list[dict[str, str]]:
        """获取漂流瓶的所有图片URL及尺寸信息

        参数:
            bottle_id: 漂流瓶ID

        返回:
            list[dict]: 包含url/width/height的字典列表
        """
        images = await BottleImage.get_images_by_bottle_id(bottle_id)
        result = []
        for img in images:
            url = await BedLayout.get_url(
                img.filename, storage_type=StorageType.LOCAL
            )
            result.append({
                "url": url,
                "width": str(img.width),
                "height": str(img.height),
            })
        return result

    @staticmethod
    async def get_bottle_image_bytes_list(
        bottle_id: int,
    ) -> list[bytes]:
        """获取漂流瓶的所有图片字节数据

        参数:
            bottle_id: 漂流瓶ID

        返回:
            list[bytes]: 图片字节数据列表
        """
        images = await BottleImage.get_images_by_bottle_id(bottle_id)
        result = []
        for img in images:
            data = await BedLayout.get_bytes(
                img.filename, storage_type=StorageType.LOCAL
            )
            if data:
                result.append(data)
        return result

    @classmethod
    async def _upload_temp_image_for_markdown(
        cls, bottle_id: int, image_data: bytes, image_index: int
    ) -> dict[str, str] | None:
        """为QQ Markdown消息上传图片到云存储（临时，自动删除）

        参数:
            bottle_id: 漂流瓶ID
            image_data: 图片二进制数据
            image_index: 图片序号

        返回:
            dict | None: 包含url/width/height的字典，失败返回None
        """
        try:
            webp_data, width, height = cls._convert_to_webp(image_data)
            ts = datetime.now().strftime("%Y%m%d%H%M%S")
            filename = (
                f"{BOTTLE_IMAGE_DIR}/{bottle_id}/"
                f"md_{image_index}_{ts}.webp"
            )
            result = await BedLayout.save_image_bytes(
                file_data=webp_data,
                filename=filename,
                extension=".webp",
                content_type="image/webp",
                delete_after_minutes=1,
            )
            image_url = result.get("url", "")
            if not image_url:
                logger.warning(
                    "上传图片到云存储失败: URL为空", "BottleMsg"
                )
                return None
            return {
                "url": image_url,
                "width": str(width),
                "height": str(height),
            }
        except Exception as e:
            logger.error(f"上传图片到云存储失败: {e}", "BottleMsg")
            return None

    @staticmethod
    async def _resolve_sender_uid(user_id: str) -> str:
        """解析发送者UID，失败回退到默认昵称

        参数:
            user_id: 用户ID

        返回:
            str: 用户UID或默认昵称
        """
        try:
            uid = await UserInfo.get_user_uid(user_id)
            return uid or Config.get_config(
                CONFIG_MODULE, "DEFAULT_NICKNAME", "未知用户"
            )
        except Exception as e:
            logger.warning(
                f"获取用户UID失败 user_id={user_id}: {e}",
                "BottleMsg",
            )
            return Config.get_config(
                CONFIG_MODULE, "DEFAULT_NICKNAME", "未知用户"
            )

    @classmethod
    async def build_normal_message(
        cls, session: Uninfo, bottle: BottleRecord
    ) -> list:
        """构建普通消息格式（非QQ官方Bot）

        参数:
            session: 会话信息
            bottle: 漂流瓶记录

        返回:
            list: 消息列表
        """
        sender = await cls._resolve_sender_uid(bottle.user_id)
        time_str = bottle.create_time.strftime("%Y-%m-%d %H:%M:%S")

        msg_parts = [f"漂流瓶ID: {bottle.id}"]
        if bottle.content:
            msg_parts.append(f"内容: {bottle.content}")
        if Config.get_config(CONFIG_MODULE, "BOTTLE_MSG_UID", True):
            msg_parts.append(f"发送者UID: {sender}")
        msg_parts.append(f"发送时间: {time_str}")

        msg_list: list = ["\n".join(msg_parts)]
        for img_bytes in await cls.get_bottle_image_bytes_list(bottle.id):
            msg_list.append(img_bytes)

        messages = [MessageUtils.build_message(msg_list)]

        comments = await BottleComment.get_approved_comments(bottle.id)
        if comments:
            comment_msg = cls._format_comments_normal(comments)
            if Config.get_config(
                CONFIG_MODULE, "BOTTLE_MSG_SPLIT", True
            ):
                messages.append(MessageUtils.build_message(comment_msg))
            else:
                messages[0] += MessageUtils.build_message(comment_msg)
        return messages

    @classmethod
    async def build_qq_markdown_message(
        cls, session: Uninfo, bottle: BottleRecord
    ) -> list:
        """构建QQ Markdown消息格式（QQ官方Bot）

        图片需要上传到云存储获取公网URL，
        瓶子本体和评论区合并在同一个模板中，用分割线分开

        参数:
            session: 会话信息
            bottle: 漂流瓶记录

        返回:
            list: 消息列表
        """
        sender = await cls._resolve_sender_uid(bottle.user_id)
        content_text = (
            bottle.content.replace("\n", "\r")
            if bottle.content
            else "什么都没写"
        )
        time_str = bottle.create_time.strftime("%Y-%m-%d %H:%M:%S")

        image_bytes_list = await cls.get_bottle_image_bytes_list(bottle.id)
        image_urls: list[dict[str, str]] = []
        for idx, img_data in enumerate(image_bytes_list):
            result = await cls._upload_temp_image_for_markdown(
                bottle.id, img_data, idx
            )
            if result:
                image_urls.append(result)

        md_parts = cls._build_markdown_body(
            bottle.id, sender, content_text, time_str, image_urls
        )

        comments = await BottleComment.get_approved_comments(bottle.id)
        if comments:
            md_parts.append(
                cls._build_markdown_comments(bottle.id, comments)
            )

        md_content = "\n\n".join(md_parts)
        buttons = cls._build_bottle_keyboard(bottle.id)
        return [MessageUtils.build_markdown_message(md_content, buttons)]

    @classmethod
    def _build_markdown_body(
        cls,
        bottle_id: int,
        sender: str,
        content_text: str,
        time_str: str,
        image_urls: list[dict[str, str]],
    ) -> list[str]:
        """构建QQ Markdown瓶子主体部分

        参数:
            bottle_id: 漂流瓶ID
            sender: 发送者UID
            content_text: 文本内容
            time_str: 时间字符串
            image_urls: 图片URL信息列表

        返回:
            list[str]: Markdown片段列表
        """
        sender_line = (
            f"UID: {sender}\n"
            if Config.get_config(CONFIG_MODULE, "BOTTLE_MSG_UID", True)
            else ""
        )
        if not image_urls:
            return [
                f"***漂流瓶***\n"
                f"> Time: {time_str}\n"
                f"ID: {bottle_id}\n"
                f"{sender_line}"
                f"{content_text}"
            ]

        first_image = image_urls[0]
        parts = [
            f"![图片 #{first_image['width']}px "
            f"#{first_image['height']}px]"
            f"({first_image['url']})\n"
            f"> Time: {time_str}\n"
            f"ID: {bottle_id}\n"
            f"{sender_line}"
            f"{content_text}"
        ]
        for img_info in image_urls[1:]:
            parts.append(
                f"![图片 #{img_info['width']}px "
                f"#{img_info['height']}px]"
                f"({img_info['url']})"
            )
        return parts

    @classmethod
    def _build_markdown_comments(
        cls, bottle_id: int, comments: list[BottleComment]
    ) -> str:
        """构建QQ Markdown评论区片段

        参数:
            bottle_id: 漂流瓶ID
            comments: 评论列表

        返回:
            str: Markdown评论文本
        """
        total = len(comments)
        max_comments = int(
            Config.get_config(CONFIG_MODULE, "MAX_BOTTLE_COMMENTS", 3)
            or 3
        )
        show_uid = Config.get_config(CONFIG_MODULE, "BOTTLE_MSG_UID", True)
        default_nick = Config.get_config(
            CONFIG_MODULE, "DEFAULT_NICKNAME", "未知用户"
        )
        display_comments = comments[:max_comments]
        comments_text = ""
        for comment in display_comments:
            user_name = comment.user_id if show_uid else default_nick
            comments_text += f"> {user_name}: {comment.content}\n"

        footer = (
            f"_... 共{total}条评论~_"
            if total > max_comments
            else ""
        )
        return (
            f"---\n\n"
            f"*****漂流瓶 {bottle_id} 的评论区*****\n"
            f"{comments_text}"
            f"{footer}"
        )

    @staticmethod
    def _format_comments_normal(
        comments: list[BottleComment],
    ) -> str:
        """格式化评论为普通文本

        参数:
            comments: 评论列表

        返回:
            str: 格式化后的评论文本
        """
        max_comments = int(
            Config.get_config(CONFIG_MODULE, "MAX_BOTTLE_COMMENTS", 3)
            or 3
        )
        show_uid = Config.get_config(CONFIG_MODULE, "BOTTLE_MSG_UID", True)
        default_nick = Config.get_config(
            CONFIG_MODULE, "DEFAULT_NICKNAME", "未知用户"
        )
        lines = ["评论区:"]
        for comment in comments[:max_comments]:
            user_name = comment.user_id if show_uid else default_nick
            lines.append(f"{user_name}: {comment.content}")

        total = len(comments)
        if total > max_comments:
            lines.append(f"... 共{total}条评论")
        return "\n".join(lines)

    @staticmethod
    def _build_bottle_keyboard(bottle_id: int) -> list[list[Button]]:
        """构建漂流瓶操作按钮

        参数:
            bottle_id: 漂流瓶ID

        返回:
            list[list[Button]]: 按钮列表（两行布局）
        """
        return [
            [
                Button(
                    flag="enter",
                    label="丢瓶子",
                    clicked_label="丢瓶子",
                    id="btn_throw",
                    text="扔瓶子",
                    permission="all",
                ),
                Button(
                    flag="enter",
                    label="捡瓶子",
                    clicked_label="捡瓶子",
                    id="btn_get",
                    text="捡瓶子",
                    permission="all",
                ),
            ],
            [
                Button(
                    flag="enter",
                    label="点赞",
                    clicked_label="点赞",
                    id="btn_like",
                    text=f"点赞漂流瓶 {bottle_id}",
                    permission="all",
                ),
                Button(
                    flag="enter",
                    label="评论",
                    clicked_label="评论",
                    id="btn_comment",
                    text=f"评论漂流瓶 {bottle_id}",
                    permission="all",
                ),
            ],
        ]

    @classmethod
    async def build_bottle_message(
        cls, session: Uninfo, bottle: BottleRecord
    ) -> list:
        """根据适配器类型构建漂流瓶消息

        参数:
            session: 会话信息
            bottle: 漂流瓶记录

        返回:
            list: 消息列表
        """
        if PlatformUtils.is_qbot(session) and not PlatformUtils.is_qq_guild(
            session
        ):
            return await cls.build_qq_markdown_message(session, bottle)
        return await cls.build_normal_message(session, bottle)
