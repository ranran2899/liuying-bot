"""TTS命令处理

注册bot说命令，调用LLM TTS能力合成语音并发送。
"""

from nonebot_plugin_alconna import (
    Alconna,
    Args,
    on_alconna,
)
from nonebot_plugin_uninfo import Uninfo

from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

from ...config import get_config
from ...core.llm import llm_helper
from ...core.persona import persona_manager
from ...core.safety.acl import AclChecker
from ..chat_helpers import ChatMatchersHelper

__all__ = ["setup_tts_commands"]

_MAX_TTS_TEXT_LENGTH = 300
"""bot说文本长度上限（字符）"""


def setup_tts_commands() -> None:
    """注册TTS合成matcher

    命令: bot说 <文本>
    使用当前用户激活的人格对应的语音配置。
    """
    tts_cmd = on_alconna(
        Alconna("bot说", Args["text", str]),
        aliases={"AI说"},
        priority=49,
        block=True,
    )

    @tts_cmd.handle()
    async def _handle_tts(
        session: Uninfo, text: str = ""
    ) -> None:
        """TTS语音合成

        使用当前用户激活的人格对应的语音配置，
        文本超长时拒绝合成。
        """
        # 黑名单用户不可触发语音合成（消耗配额且直发音频）
        if await AclChecker.check_blacklist(
            session.user.id,
            session.scene.id if session.scene.is_group else None,
        ):
            return

        # TTS 配置只读取一次，供开关与音色兜底共用
        tts_cfg = get_config("TTS", {})
        if not tts_cfg.get("enabled", False):
            await MessageUtils.build_message("TTS功能未启用").finish()
            return

        if not text:
            await MessageUtils.build_message(
                "请输入要合成的文本"
            ).finish()
            return

        if len(text) > _MAX_TTS_TEXT_LENGTH:
            await MessageUtils.build_message(
                f"文本太长了（{len(text)}字），"
                f"语音合成上限{_MAX_TTS_TEXT_LENGTH}字，"
                "请精简后再试"
            ).finish()
            return

        err_msg = ""
        audio = None
        try:
            persona = await persona_manager.get_user_persona_config(
                session.user.id
            )
            tts_config = persona_manager.get_persona_tts_config(persona)
            voice = tts_config.get(
                "voice", tts_cfg.get("voice", "alloy")
            )
            audio = await llm_helper.tts(text, voice=voice)
        except Exception as e:
            logger.warning(
                f"TTS合成失败: {e}", command="AI", e=e
            )
            err_msg = "TTS合成失败"

        if err_msg:
            await MessageUtils.build_message(err_msg).finish()
            return

        if audio:
            await ChatMatchersHelper._send_reply(
                session, "", tts_audio=audio
            )
        else:
            await MessageUtils.build_message("语音合成失败").finish()
