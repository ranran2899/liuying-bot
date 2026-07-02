"""对话matcher辅助工具

提供用户AI对话开关状态管理器与会话文本构建、图片描述提取、
回复发送、群禁言notice注册等辅助能力。
"""

import asyncio
from pathlib import Path
from typing import Any

from nonebot import on_notice
from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import Image
from nonebot_plugin_uninfo import Uninfo

from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

from ..core.group import update_group_mute_from_notice
from ..core.tools import (
    extract_image_segments,
    fetch_image_bytes,
)
from ..core.vision import summarize_image

__all__ = [
    "ChatMatchersHelper",
    "_ai_user_states",
]


class _AIUserStateManager:
    """用户AI对话开关状态管理器

    线程安全地管理用户级AI对话开关状态。
    """

    def __init__(self) -> None:
        """初始化状态管理器"""
        self._states: dict[str, bool] = {}

    def is_enabled(self, user_id: str) -> bool:
        """检查用户AI对话是否启用

        参数:
            user_id: 用户ID

        返回:
            bool: 是否启用
        """
        return self._states.get(user_id, True)

    def set_state(self, user_id: str, enabled: bool) -> None:
        """设置用户AI对话开关状态

        参数:
            user_id: 用户ID
            enabled: 是否启用
        """
        self._states[user_id] = enabled


_ai_user_states = _AIUserStateManager()
"""用户AI对话开关状态单例"""


class ChatMatchersHelper:
    """对话matcher辅助工具类

    封装会话文本构建、图片描述提取、回复发送等辅助方法。
    """

    @staticmethod
    def _build_session_text(text: str) -> str:
        """构建会话文本

        参数:
            text: 原始文本

        返回:
            str: 清理后的文本
        """
        return text.strip()

    @staticmethod
    async def _describe_single_image(
        img: dict[str, Any]
    ) -> str:
        """描述单张图片（下载 + 视觉理解）

        参数:
            img: 图片段字典，含 url/path/raw 字段

        返回:
            str: 描述文本，失败返回空串
        """
        image_data = await fetch_image_bytes(
            url=img.get("url", ""),
            path=img.get("path", ""),
            raw=img.get("raw"),
        )
        if not image_data:
            return ""
        try:
            summary = await summarize_image(image_data)
            if summary.success and summary.description:
                return summary.description
        except Exception as e:
            logger.debug(
                f"图片理解失败: {e}", command="AI", e=e
            )
        return ""

    @staticmethod
    async def _extract_image_descriptions(
        event: Event,
    ) -> list[str]:
        """从消息事件提取图片并生成描述

        多张图片并行处理（asyncio.gather），避免串行耗时。

        参数:
            event: 消息事件

        返回:
            list[str]: 图片描述列表（与图片顺序对齐）
        """
        images = extract_image_segments(event)
        if not images:
            return []

        tasks = [
            ChatMatchersHelper._describe_single_image(img)
            for img in images
        ]
        results = await asyncio.gather(*tasks)
        return [desc for desc in results if desc]

    @staticmethod
    async def _send_reply(
        session: Uninfo,
        text: str,
        sticker: Image | bytes | Path | None = None,
        tts_audio: bytes | None = None,
        image_url: str | None = None,
        segments: list[str] | None = None,
        gap_delays: list[float] | None = None,
    ) -> None:
        """发送回复消息（支持碎片化分段与图片）

            统一使用 MessageUtils.build_message 构建消息。

            参数:
                session: 会话信息
                text: 回复文本（segments为空时使用）
                sticker: 贴纸图片对象/路径/字节
                tts_audio: TTS音频
                image_url: 生成图片的URL
                segments: 碎片化段列表（非空时优先使用）
                gap_delays: 段间延迟列表（与segments对齐）
            """
        if segments and not image_url:
            last_idx = len(segments) - 1
            for i, seg in enumerate(segments):
                if not seg:
                    continue
                await MessageUtils.build_message(seg).send()
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

        msg_parts: list[Any] = []
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
    def _register_group_ban_notice() -> None:
        """注册 group_ban notice 监听以感知群禁言状态"""
        try:
            notice_matcher = on_notice(
                priority=50, block=False
            )

            @notice_matcher.handle()
            async def _handle_group_ban(
                bot: Bot, event: Event
            ) -> None:
                """处理 group_ban notice 事件"""
                notice_type = str(
                    getattr(event, "notice_type", "") or ""
                ).strip()
                if notice_type != "group_ban":
                    return

                self_id = str(
                    getattr(bot, "self_id", "") or ""
                )
                updated = update_group_mute_from_notice(
                    event, bot_self_id=self_id
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
        except Exception as e:
            logger.warning(
                f"注册 group_ban notice 监听失败: {e}",
                command="AI",
                e=e,
            )
