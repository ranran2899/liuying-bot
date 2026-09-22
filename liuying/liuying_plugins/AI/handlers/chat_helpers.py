"""对话matcher辅助工具

提供图片描述提取、回复发送、群禁言notice处理等辅助能力。
"""

import asyncio
from pathlib import Path
from typing import Any

from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import At, Image, Reply, UniMsg
from nonebot_plugin_uninfo import Uninfo

from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

from ..core.group import GroupMuteTracker
from ..core.tools import MessageExtractor

__all__ = [
    "ChatMatchersHelper",
]


def _detect_image_mime(data: bytes) -> str:
    """根据魔数字推断图片 MIME 类型

    参数:
        data: 图片二进制数据

    返回:
        str: MIME 类型，无法识别时回退 image/jpeg
    """
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:2] == b"BM":
        return "image/bmp"
    return "image/jpeg"


class ChatMatchersHelper:
    """对话matcher辅助工具类

    封装图片描述提取、回复发送、群禁言notice处理等辅助方法。
    """

    @staticmethod
    def extract_images(
        message: UniMsg,
    ) -> list[dict[str, Any]]:
        """从统一消息提取图片URL

        接收到的图片均为服务器直链（如QQ多媒体服务器）。

        参数:
            message: alconna注入的统一消息

        返回:
            list[dict[str, Any]]: 图片信息列表（url）
        """
        return [
            {"url": str(seg.url or ""), "path": "", "raw": None}
            for seg in message
            if isinstance(seg, Image) and seg.url
        ]

    @staticmethod
    async def extract_first_image(
        message: UniMsg,
    ) -> tuple[bytes, str] | None:
        """提取消息中首张图片的二进制与 MIME 类型

        多模态直传路径：只取首张图片供下游视觉路由使用（
        与旧版多图片文本描述相比简化为单图，符合多模态消息约定）。

        参数:
            message: alconna注入的统一消息

        返回:
            tuple[bytes, str] | None: (图片数据, mime)，无图或下载失败时 None
        """
        images = ChatMatchersHelper.extract_images(message)
        if not images:
            return None
        img = images[0]
        image_data = await MessageExtractor.fetch_image_bytes(
            url=img.get("url", ""),
            path=img.get("path", ""),
            raw=img.get("raw"),
        )
        if not image_data:
            return None
        return image_data, _detect_image_mime(image_data)

    @staticmethod
    async def send_reply(
        session: Uninfo,
        text: str,
        sticker: Image | bytes | Path | None = None,
        tts_audio: bytes | None = None,
        image_url: str | None = None,
        segments: list[str] | None = None,
        gap_delays: list[float] | None = None,
        *,
        quote_msg_id: int | None = None,
        at_user_id: str | None = None,
    ) -> None:
        """发送回复消息（支持碎片化分段与图片）

        统一使用 MessageUtils.build_message 构建消息。
        quote_msg_id/at_user_id 仅作用于第一条段，避免每段都引用/@。

        参数:
            session: 会话信息
            text: 回复文本（segments为空时使用）
            sticker: 贴纸图片对象/路径/字节
            tts_audio: TTS音频
            image_url: 生成图片的URL
            segments: 碎片化段列表（非空时优先使用）
            gap_delays: 段间延迟列表（与segments对齐）
            quote_msg_id: 引用回复的消息ID，None为不引用
            at_user_id: @的用户ID，None为不@
        """
        # 归一化分段：过滤空串，全空则视为无分段
        segments = [s for s in (segments or []) if s] or None

        def _build_prefix_parts(idx: int) -> list:
            """构造首条段的引用/@前缀段

            参数:
                idx: 段索引，仅0时构造

            返回:
                list: 前缀段列表（可能为空）
            """
            if idx != 0:
                return []
            parts: list = []
            if quote_msg_id is not None:
                parts.append(Reply(id=quote_msg_id))
            if at_user_id is not None:
                parts.append(At(flag="user", target=at_user_id))
            return parts

        if segments and not image_url:
            last_idx = len(segments) - 1
            for i, seg in enumerate(segments):
                if not seg:
                    continue
                parts = _build_prefix_parts(i)
                parts.append(seg)
                await MessageUtils.build_message(parts).send()
                if i < last_idx and gap_delays:
                    delay = (
                        gap_delays[i]
                        if i < len(gap_delays)
                        else 0.0
                    )
                    if delay > 0:
                        await asyncio.sleep(delay)

            if sticker:
                await MessageUtils.build_message(sticker).send()
            if tts_audio:
                await MessageUtils.build_message(tts_audio).send()
            return

        if (
            not text
            and not sticker
            and not tts_audio
            and not image_url
        ):
            return

        msg_parts: list = _build_prefix_parts(0)
        if text:
            msg_parts.append(text)
        if image_url:
            msg_parts.append(Image(url=image_url))
        if sticker:
            msg_parts.append(sticker)
        if tts_audio:
            msg_parts.append(tts_audio)

        await MessageUtils.build_message(msg_parts).send()

    @staticmethod
    async def handle_group_ban(bot: Bot, event: Event) -> None:
        """处理 group_ban notice 事件

        参数:
            bot: Bot对象
            event: 事件对象
        """
        notice_type = str(
            getattr(event, "notice_type", "") or ""
        ).strip()
        if notice_type != "group_ban":
            return

        self_id = str(
            getattr(bot, "self_id", "") or ""
        )
        updated = (
            GroupMuteTracker.update_group_mute_from_notice(
                event, bot_self_id=self_id
            )
        )
        if updated:
            group_id = str(
                getattr(event, "group_id", "") or ""
            )
            duration = int(
                getattr(event, "duration", 0) or 0
            )
            logger.info(
                f"收到群禁言通知: group={group_id} "
                f"duration={duration}s",
                command="AI",
                group_id=group_id,
            )
