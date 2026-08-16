"""回复决策组件

从 ReplyProcessor 提取的辅助决策逻辑，包括：
- 贴纸决策（选择与记录使用）
- TTS决策（概率触发语音合成）
- 沉默表情表态决策
- 输入状态模拟决策
- 人格口头禅前置决策

所有方法均为静态方法，依赖模块级单例，无实例状态。
"""

import random
from typing import Any

from nonebot_plugin_alconna import Image

from liuying.utils.log import logger

from ..agent.runner import AgentResult
from ..config import get_config
from ..core.emotion.manager import emotion_manager
from ..core.llm import llm_helper
from ..core.persona import persona_manager
from .humanize import HumanizeToolkit
from .sticker import sticker_manager
from .types import ReplyContext

_TTS_AUTO_TEXT_MIN_LEN = 5
"""自动TTS最小文本长度"""

__all__ = ["ReplyDecisions"]


class ReplyDecisions:
    """回复辅助决策集合

    封装从 ReplyProcessor 提取的辅助决策逻辑。
    所有方法均为静态方法，通过模块级单例访问依赖服务。
    """

    @staticmethod
    async def decide_sticker(
        text: str,
        ctx: ReplyContext,
        agent_result: AgentResult | None = None,
        persona: dict[str, Any] | None = None,
    ) -> Image | None:
        """贴纸决策

        优先使用 agent_result.response.sticker_mood_hint；
        同时传入 user_id 以便策展器记录偏好。

        参数:
            text: 回复文本
            ctx: 回复上下文
            agent_result: Agent结果（用于提取情绪提示）
            persona: 调用方透传的用户人格配置，
                None时自行获取（兼容独立调用）

        返回:
            Image | None: 贴纸图片对象，不发时返回None
        """
        try:
            persona = (
                persona
                or await persona_manager.get_user_persona_config(
                    ctx.user_id
                )
            )
            persona_mood = persona_manager.get_persona_sticker_mood(
                persona
            )
            mood_hint = ""
            if agent_result and agent_result.response:
                mood_hint = agent_result.response.sticker_mood_hint
            item = await sticker_manager.choose_reply_sticker_item(
                text,
                persona_mood=persona_mood,
                mood_hint=mood_hint,
                group_id=ctx.group_id,
                is_private=ctx.is_private,
                user_id=ctx.user_id,
            )
            if not item:
                return None
            await sticker_manager.record_usage(
                sticker_id=item.id,
                context_text=text,
                detected_mood=mood_hint or persona_mood,
                persona_mood=persona_mood,
                group_id=ctx.group_id or "",
                user_id=ctx.user_id,
                bot_id=ctx.bot_id or "",
            )
            return await sticker_manager.item_to_image(item)
        except Exception as e:
            logger.debug(
                f"贴纸决策失败: {e}", command="AI", e=e
            )
            return None

    @staticmethod
    async def decide_tts(
        text: str,
        ctx: ReplyContext,
        persona: dict[str, Any] | None = None,
    ) -> bytes | None:
        """TTS决策

        根据配置概率自动将回复文本合成语音。
        仅在 TTS_ENABLED 与 TTS_AUTO_ENABLED 均开启时触发，
        文本长度需达到 _TTS_AUTO_TEXT_MIN_LEN 阈值。

        参数:
            text: 回复文本
            ctx: 回复上下文
            persona: 调用方透传的用户人格配置，
                None时自行获取（兼容独立调用）

        返回:
            bytes | None: 音频数据，不发时返回None
        """
        tts_cfg = get_config("TTS", {})
        tts_auto_cfg = get_config("TTS_AUTO", {})
        if not tts_cfg.get("enabled", False) or not tts_auto_cfg.get(
            "enabled", False
        ):
            return None
        if len(text) < _TTS_AUTO_TEXT_MIN_LEN:
            return None

        if random.random() >= tts_auto_cfg.get("probability", 0.2):
            return None
        try:
            persona = (
                persona
                or await persona_manager.get_user_persona_config(
                    ctx.user_id
                )
            )
            tts_config = persona_manager.get_persona_tts_config(
                persona
            )
            voice = tts_config.get(
                "voice", tts_cfg.get("voice", "alloy")
            )
            return await llm_helper.tts(text, voice=voice)
        except Exception as e:
            logger.debug(
                f"TTS决策失败: {e}", command="AI", e=e
            )
            return None

    @staticmethod
    def decide_silence_reaction(
        ctx: ReplyContext,
    ) -> int | None:
        """沉默时按概率决定表情表态face_id

        仅群聊 + REACTION_ENABLED + 概率命中时返回face_id，
        由发送方拿到message_id后调用ProtocolHelper.emoji_react执行。

        参数:
            ctx: 回复上下文

        返回:
            int | None: face_id，None为不表态
        """
        if not ctx.group_id:
            return None
        if not get_config("REACTION", {}).get("enabled", True):
            return None
        prob = get_config("REACTION", {}).get("probability", 0.15)
        if random.random() >= prob:
            return None
        return HumanizeToolkit.pick_reaction_face_id("neutral")

    @staticmethod
    def decide_typing_status(
        ctx: ReplyContext, typing_delay: float
    ) -> bool:
        """判断是否需要模拟输入状态

        仅私聊 + INPUT_STATUS_ENABLED + 延迟>1.5s时触发，
        避免在群聊刷屏输入状态打扰他人。

        参数:
            ctx: 回复上下文
            typing_delay: 打字延迟（秒）

        返回:
            bool: 是否需要模拟输入状态
        """
        if not ctx.is_private:
            return False
        if not get_config("INPUT_STATUS_ENABLED", False):
            return False
        return typing_delay > 1.5

    @staticmethod
    async def maybe_prepend_catchphrase(
        text: str,
        ctx: ReplyContext,
        persona: dict[str, Any] | None = None,
    ) -> str:
        """按概率在回复前插入人格口头禅

        从用户当前人格的traits.catchphrase列表按概率前置插入。
        失败时返回原始文本，不影响主流程。

        参数:
            text: 拟人化后的回复文本
            ctx: 回复上下文
            persona: 调用方透传的用户人格配置，
                None时自行获取（兼容独立调用）

        返回:
            str: 可能前置了口头禅的文本
        """
        persona = (
            persona
            or await persona_manager.get_user_persona_config(
                ctx.user_id
            )
        )
        traits = persona.get("traits") or {}
        if not isinstance(traits, dict):
            return text
        catchphrases = traits.get("catchphrase") or []
        if not catchphrases or not isinstance(
            catchphrases, list
        ):
            return text
        state = await emotion_manager.get_state(
            ctx.user_id, ctx.group_id, persona_name=ctx.persona_name
        )
        mood = (state.mood if state else "neutral") or "neutral"
        return HumanizeToolkit.maybe_prepend_catchphrase(
            text, catchphrases, mood=mood
        )
