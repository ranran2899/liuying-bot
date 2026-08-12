"""聊天命令处理

注册私聊/@bot消息触发的AI对话matcher，统一处理回复生成与发送。
"""

import asyncio

from nonebot import get_bot, on_message
from nonebot.adapters import Event
from nonebot.rule import to_me
from nonebot_plugin_uninfo import Uninfo

from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

from ...config import get_config
from ...core.group import group_social
from ...core.peer_awareness import peer_awareness
from ...core.runtime import ProtocolHelper, runtime_switch
from ...core.safety import AclChecker
from ...core.target_inference import MessageTarget, target_inference
from ...core.tools import MessageExtractor
from ...pipeline.processor import ReplyResult, reply_processor
from ...pipeline.reply_buffer import reply_buffer
from ..chat_helpers import ChatMatchersHelper, _ai_user_states

__all__ = ["setup_chat_commands"]


async def _apply_emoji_react(
    session: Uninfo, message_id: int, face_id: int
) -> None:
    """执行表情表态

    协议扩展调用降级：失败仅记录debug日志，不影响主流程。

    参数:
        session: 会话信息
        message_id: 消息ID
        face_id: 表情ID
    """
    try:
        bot = get_bot()
        await ProtocolHelper.emoji_react(
            bot,
            message_id=message_id,
            face_id=face_id,
            group_id=(
                session.scene.id if session.scene.is_group else ""
            ),
        )
    except Exception as e:
        logger.debug(
            f"表情表态失败: {e}", command="AI", e=e
        )


async def _apply_set_typing(session: Uninfo) -> None:
    """执行输入状态模拟

    协议扩展调用降级：失败仅记录debug日志，不影响主流程。

    参数:
        session: 会话信息
    """
    try:
        bot = get_bot()
        await ProtocolHelper.set_typing(
            bot, user_id=session.user.id
        )
    except Exception as e:
        logger.debug(
            f"输入状态模拟失败: {e}", command="AI", e=e
        )


def setup_chat_commands() -> None:
    """注册聊天对话matcher

    使用 to_me() 规则：私聊自动命中，
    群聊中@bot或回复bot时命中。
    """
    _register_peer_bot_listener()
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
        text = MessageExtractor.extract_message_text(event)

        # 群聊目标推断：当消息明确@他人或回复他人时跳过，避免误回复
        if (
            not is_private
            and get_config("TARGET_INFERENCE_ENABLED", True)
        ):
            target = target_inference.infer_message_target(
                event, bot_self_id=session.self_id
            )
            if target == MessageTarget.OTHERS:
                logger.debug(
                    f"群消息目标为他人，跳过回复: "
                    f"group={group_id} user={user_id}",
                    command="AI",
                )
                return

        image_descs: list[str] = []
        if get_config("VISION", {}).get("enabled", True):
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

        # 消息批量缓冲：合并短时间内的多条消息
        if get_config("REPLY_BUFFER", {}).get("enabled", True):
            session_key = (
                f"private:{user_id}"
                if is_private
                else f"group:{group_id}:{user_id}"
            )
            combined = await reply_buffer.submit(
                session_key=session_key,
                text=text,
                is_private=is_private,
                message_id=getattr(event, "message_id", None),
            )
            if combined is None:
                # 已被合并到前一条消息，跳过处理
                return
            text = combined

        await _handle_reply(
            session,
            user_id,
            text,
            group_id,
            is_private,
            message_id=getattr(event, "message_id", None),
        )

    async def _handle_reply(
        session: Uninfo,
        user_id: str,
        text: str,
        group_id: str | None,
        is_private: bool,
        message_id: int | None = None,
    ) -> None:
        """统一处理回复生成与发送

        参数:
            session: 会话信息
            user_id: 用户ID
            text: 输入文本
            group_id: 群组ID
            is_private: 是否私聊
            message_id: 触发消息的ID，用于引用回复/表情表态
        """
        err_text = ""
        result: ReplyResult | None = None
        try:
            # ACL黑名单检查（拉黑用户/群组不响应）
            if await AclChecker.check_blacklist(user_id, group_id):
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
                group_social.record_message(
                    group_id=group_id,
                    user_id=user_id,
                    text=text,
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
                f"AI对话处理失败：{e}",
                command="流萤",
                e=e,
            )
            err_text = "出了点小问题，待会再试试~"

        if err_text:
            await MessageUtils.build_message(err_text).finish()
            return

        if result is None:
            return

        if result.metadata.get("silence"):
            # 沉默时仍可能按概率表情表态
            if (
                result.react_face_id is not None
                and message_id is not None
            ):
                await _apply_emoji_react(
                    session,
                    message_id,
                    result.react_face_id,
                )
            return

        # 全空串分段视为无分段，避免静默丢失消息/引用
        if result.segments and all(
            not s for s in result.segments
        ):
            result.segments = None

        if not result.text and not result.segments:
            return

        # 输入状态模拟与发送（异常兜底，避免 matcher 静默崩溃）
        try:
            if result.should_set_typing:
                await _apply_set_typing(session)

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
                quote_msg_id=(
                    message_id if result.should_quote else None
                ),
                at_user_id=result.at_user_id,
            )
        except Exception as e:
            logger.error(
                f"AI回复发送失败：{e}", command="流萤", e=e
            )
            await MessageUtils.build_message(
                "出了点小问题，待会再试试~"
            ).send()


def _register_peer_bot_listener() -> None:
    """注册群消息监听器用于检测其他bot发言

    在群消息中识别其他bot发言并触发静默，避免bot互相对话。
    监听器优先级较高（priority=100），不阻断后续matcher。
    """
    peer_cmd = on_message(priority=100, block=False)

    @peer_cmd.handle()
    async def _handle_peer_detection(
        event: Event,
        session: Uninfo,
    ) -> None:
        """检测群内其他bot发言并触发静默

        参数:
            event: 消息事件
            session: 会话信息
        """
        if not get_config("PEER_AWARENESS_ENABLED", True):
            return
        if not session.scene.is_group:
            return
        group_id = session.scene.id
        user_id = session.user.id
        if user_id == session.self_id:
            return
        text = MessageExtractor.extract_message_text(event)
        if not text:
            return
        nickname = (
            session.user.nick
            or session.user.name
            or ""
        )
        if peer_awareness.is_peer_bot(
            user_id=user_id,
            text=text,
            group_id=group_id,
            nickname=nickname,
        ):
            peer_awareness.trigger_silence(group_id)
