"""聊天命令处理

注册私聊/@bot消息触发的AI对话matcher，统一处理回复生成与发送。
"""

import asyncio

from nonebot import on_message
from nonebot.adapters import Event
from nonebot.rule import to_me
from nonebot_plugin_uninfo import Uninfo

from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

from ...config import get_config
from ...core.group import group_social
from ...core.runtime import runtime_switch
from ...core.safety import check_blacklist
from ...core.tools import extract_message_text
from ...pipeline.processor import ReplyResult, reply_processor
from ..chat_helpers import ChatMatchersHelper, _ai_user_states

__all__ = ["setup_chat_commands"]


def setup_chat_commands() -> None:
    """注册聊天对话matcher

    使用 to_me() 规则：私聊自动命中，
    群聊中@bot或回复bot时命中。
    """
    private_msg_cmd = on_message(
        rule=to_me(), priority=520, block=False
    )

    @private_msg_cmd.handle()
    async def _handle_private_message(
        event: Event,
        session: Uninfo,
    ) -> None:
        """处理私聊或@bot/回复bot的消息

        使用 nonebot 的 to_me() 规则：私聊自动命中，
        群聊中@bot或回复bot时命中。
        """
        if not get_config("ENABLE_AI", True):
            return

        user_id = session.user.id
        if not _ai_user_states.is_enabled(user_id):
            return

        group_id = (
            session.scene.id if session.scene.is_group else None
        )

        # 运行时开关检查
        if not runtime_switch.is_enabled(
            "ai", user_id=user_id, group_id=group_id
        ):
            return

        is_private = not session.scene.is_group
        text = extract_message_text(event)

        image_descs: list[str] = []
        if get_config("VISION_ENABLED", True):
            image_descs = (
                await ChatMatchersHelper._extract_image_descriptions(
                    event
                )
            )

        if image_descs:
            desc_text = "\n".join(
                f"[图片{i + 1}] {d}"
                for i, d in enumerate(image_descs)
            )
            text = (
                f"{text}\n{desc_text}".strip()
                if text
                else desc_text
            )

        if not text:
            return

        label = "AI私聊消息" if is_private else "AI@消息"
        logger.info(
            f"{label}: {text[:50]}",
            command="流萤",
            session=session,
        )

        await _handle_reply(
            session,
            user_id,
            text,
            group_id,
            is_private,
        )

    async def _handle_reply(
        session: Uninfo,
        user_id: str,
        text: str,
        group_id: str | None,
        is_private: bool,
    ) -> None:
        """统一处理回复生成与发送

        参数:
            session: 会话信息
            user_id: 用户ID
            text: 输入文本
            group_id: 群组ID
            is_private: 是否私聊
        """
        err_text = ""
        result: ReplyResult | None = None
        try:
            # ACL黑名单检查（拉黑用户/群组不响应）
            if await check_blacklist(user_id, group_id):
                logger.debug(
                    f"用户/群组在黑名单，跳过回复: "
                    f"user={user_id} group={group_id}",
                    command="AI",
                )
                return

            # 记录用户消息到群社交智能（仅群聊）
            if group_id and get_config(
                "SOCIAL_INTELLIGENCE_ENABLED", True
            ):
                try:
                    group_social.record_message(
                        group_id=group_id,
                        user_id=user_id,
                        text=text,
                    )
                except Exception as e:
                    logger.debug(
                        f"群社交记录失败: {e}",
                        command="AI",
                        e=e,
                    )

            result = await reply_processor.handle_text(
                user_id=user_id,
                text=text,
                group_id=group_id,
                platform=session.platform,
                bot_id=session.self_id,
                is_private=is_private,
            )
        except Exception as e:
            logger.error(
                f"AI对话处理失败: {e}",
                command="流萤",
                e=e,
                session=session,
            )
            err_text = "出了点小问题，待会再试试~"

        if err_text:
            await MessageUtils.build_message(err_text).finish()
            return

        if result is None:
            return

        if result.metadata.get("silence"):
            return

        if not result.text and not result.segments:
            return

        if result.typing_delay > 0:
            await asyncio.sleep(result.typing_delay)

        await ChatMatchersHelper._send_reply(
            session,
            result.text,
            result.sticker,
            result.tts_audio,
            image_url=result.image_url,
            segments=result.segments or None,
            gap_delays=result.gap_delays or None,
        )
