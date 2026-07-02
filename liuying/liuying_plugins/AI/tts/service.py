"""TTS服务实现

封装LLM TTS能力，提供语音合成、自动TTS决策、人格配置提取等。
"""

import random

from liuying.utils.log import logger

from ..config import get_config
from ..core.llm import llm_helper
from ..core.persona import persona_manager

_AUTO_TTS_MIN_LEN = 5
"""自动TTS最小文本长度"""

_AUTO_TTS_MAX_LEN = 200
"""自动TTS最大文本长度"""


class TTSService:
    """TTS语音服务

    封装LLM的TTS能力，提供自动决策与手动合成接口。
    """

    def is_enabled(self) -> bool:
        """检查TTS是否启用

        返回:
            bool: 是否启用
        """
        return bool(get_config("TTS_ENABLED", False))

    def is_auto_enabled(self) -> bool:
        """检查自动TTS是否启用

        返回:
            bool: 是否启用自动TTS
        """
        return bool(
            get_config("TTS_ENABLED", False)
            and get_config("TTS_AUTO_ENABLED", False)
        )

    def should_auto_tts(
        self,
        text: str,
        user_id: str | None = None,
        group_id: str | None = None,
    ) -> bool:
        """决策是否自动发送TTS

        参数:
            text: 回复文本
            user_id: 用户ID
            group_id: 群组ID

        返回:
            bool: 是否发送TTS
        """
        if not self.is_auto_enabled():
            return False
        if not text or len(text) < _AUTO_TTS_MIN_LEN:
            return False
        if len(text) > _AUTO_TTS_MAX_LEN:
            return False
        return random.random() < float(
            get_config("TTS_AUTO_PROBABILITY", 0.2)
        )

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        model: str | None = None,
    ) -> bytes | None:
        """语音合成

        参数:
            text: 合成文本
            voice: 音色，None时用配置默认
            model: TTS模型名

        返回:
            bytes | None: 音频数据，失败返回None
        """
        if not text:
            return None
        try:
            use_voice = voice or get_config("TTS_VOICE", "alloy")
            return await llm_helper.tts(text, voice=use_voice, model=model)
        except Exception as e:
            logger.warning(
                f"TTS合成失败: {e}", command="AI", e=e
            )
            return None

    async def handle_tts_command(
        self,
        text: str,
        persona_name: str | None = None,
    ) -> bytes | None:
        """处理TTS命令

        参数:
            text: 要合成的文本
            persona_name: 指定人格，None时用默认

        返回:
            bytes | None: 音频数据，失败返回None
        """
        if not get_config("TTS_ENABLED", False):
            return None

        try:
            if persona_name:
                persona = persona_manager.load_persona(persona_name)
            else:
                persona = persona_manager.get_default_persona()
            tts_config = persona_manager.get_persona_tts_config(persona)
            voice = tts_config.get(
                "voice", get_config("TTS_VOICE", "alloy")
            )
            return await self.synthesize(text, voice=voice)
        except FileNotFoundError as e:
            logger.warning(
                f"人格不存在: {persona_name} - {e}",
                command="AI",
                e=e,
            )
            return None
        except Exception as e:
            logger.warning(
                f"处理TTS命令失败: {e}", command="AI", e=e
            )
            return None

    def get_persona_tts_config(self, persona: dict | None = None) -> dict:
        """获取人格TTS配置

        参数:
            persona: 人格配置，None时用默认

        返回:
            dict: TTS配置（voice/model等）
        """
        if persona is None:
            persona = persona_manager.get_default_persona()
        return persona_manager.get_persona_tts_config(persona)


tts_service = TTSService()
"""TTS服务单例"""
