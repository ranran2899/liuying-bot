"""TTS增强服务

在基础TTS服务之上提供LLM决策、风格规划、声音克隆（预留）、
内容安全过滤等增强能力。
"""

import json
from typing import Any

from liuying.utils.log import logger

from ..config import get_config
from ..core.llm import llm_helper
from ..core.safety.filter import detect_refusal
from .service import tts_service

_UNSAFE_KEYWORDS: tuple[str, ...] = (
    "自杀", "自残", "色情", "暴力", "毒品",
    "政治敏感", "传销", "诈骗",
)
"""TTS不安全关键词集合"""

_MAX_DECISION_TEXT_LEN = 300
"""LLM决策TTS最大文本长度"""

_STYLE_DEFAULT_SPEED: float = 1.0
"""默认语速"""

_STYLE_DEFAULT_PITCH: float = 0.0
"""默认音调偏移"""


class EnhancedTTS:
    """增强TTS服务

    提供LLM决策、风格规划、声音克隆（预留）、内容安全过滤等能力。
    """

    def is_enabled(self) -> bool:
        """检查增强TTS是否启用

        返回:
            bool: 是否启用
        """
        return bool(get_config("TTS_ENABLED", False))

    def is_llm_decision_enabled(self) -> bool:
        """检查LLM决策TTS是否启用

        返回:
            bool: 是否启用LLM决策
        """
        return bool(
            self.is_enabled()
            and get_config("TTS_LLM_DECISION_ENABLED", False)
        )

    def check_safety(self, text: str) -> bool:
        """检查TTS内容安全

        通过关键词黑名单与拒绝模板正则双重过滤。
        命中不安全内容返回False。

        参数:
            text: 待检查文本

        返回:
            bool: 是否安全
        """
        if not text:
            return False
        if detect_refusal(text):
            return False
        lowered = text.lower()
        for keyword in _UNSAFE_KEYWORDS:
            if keyword in lowered:
                return False
        return True

    async def decide_tts(self, text: str, context: str) -> bool:
        """LLM决策是否适合发语音

        结合文本特征与LLM判断是否适合TTS发送。
        关闭LLM决策时回退到基础规则（长度/概率）。

        参数:
            text: 待合成文本
            context: 对话上下文

        返回:
            bool: 是否适合发语音
        """
        if not self.is_enabled() or not text:
            return False
        if not self.check_safety(text):
            return False
        if len(text) > _MAX_DECISION_TEXT_LEN:
            return False

        if not self.is_llm_decision_enabled():
            return tts_service.should_auto_tts(text)

        try:
            return await self._llm_decide(text, context)
        except Exception as e:
            logger.warning(
                f"LLM决策TTS失败，回退规则: {e}",
                command="AI",
                e=e,
            )
            return tts_service.should_auto_tts(text)

    async def _llm_decide(
        self, text: str, context: str
    ) -> bool:
        """调用LLM判断是否适合发语音

        参数:
            text: 待合成文本
            context: 对话上下文

        返回:
            bool: 是否适合发语音
        """
        prompt = (
            "请判断以下回复是否适合以语音形式发送给用户。\n"
            "适合语音的标准：简短对话、问候、情绪表达、口语化内容；\n"
            "不适合的标准：长篇说明、含代码/URL/数学公式、"
            "结构化列表、需要视觉阅读的内容。\n"
            "只输出 true 或 false，不要解释。\n\n"
            f"上下文: {context[:200]}\n"
            f"回复: {text[:200]}"
        )
        messages = [
            {
                "role": "system",
                "content": "你是TTS适配性判断助手，只输出布尔值。",
            },
            {"role": "user", "content": prompt},
        ]
        result = await llm_helper.chat_text(messages)
        answer = (result or "").strip().lower()
        return answer.startswith("true")

    async def plan_style(
        self, emotion: str, content: str
    ) -> dict[str, Any]:
        """根据情绪和上下文规划语音风格

        输出包含 voice/speed/pitch/energy 的风格字典。
        LLM不可用时回退到情绪映射表。

        参数:
            emotion: 情绪标签（如 happy/sad/angry/neutral）
            content: 内容文本

        返回:
            dict: 风格配置
        """
        fallback = self._fallback_style(emotion)
        if not self.is_enabled():
            return fallback
        try:
            return await self._llm_plan_style(emotion, content)
        except Exception as e:
            logger.debug(
                f"LLM规划风格失败，回退映射: {e}",
                command="AI",
                e=e,
            )
            return fallback

    async def _llm_plan_style(
        self, emotion: str, content: str
    ) -> dict[str, Any]:
        """调用LLM规划语音风格

        参数:
            emotion: 情绪标签
            content: 内容文本

        返回:
            dict: 风格配置
        """
        prompt = (
            "请根据情绪和内容规划语音合成风格，"
            '输出JSON：{"voice": str, "speed": float, '
            '"pitch": float, "energy": float}。\n'
            "speed范围0.5-2.0，pitch范围-1.0到1.0，"
            "energy范围0.0-1.0。\n"
            "只输出JSON，不要解释。\n\n"
            f"情绪: {emotion}\n"
            f"内容: {content[:200]}"
        )
        messages = [
            {
                "role": "system",
                "content": "你是语音风格规划助手，输出纯JSON。",
            },
            {"role": "user", "content": prompt},
        ]
        result = await llm_helper.chat_text(messages)
        text = (result or "").strip()
        try:
            style = json.loads(text)
        except json.JSONDecodeError:
            try:
                start = text.find("{")
                end = text.rfind("}") + 1
                if start >= 0 and end > start:
                    style = json.loads(text[start:end])
                else:
                    return self._fallback_style(emotion)
            except Exception:
                return self._fallback_style(emotion)
        return self._normalize_style(style, emotion)

    def _fallback_style(self, emotion: str) -> dict[str, Any]:
        """情绪到风格的映射回退方案

        参数:
            emotion: 情绪标签

        返回:
            dict: 风格配置
        """
        emotion = (emotion or "").lower()
        default_voice = str(get_config("TTS_VOICE", "alloy"))
        table: dict[str, dict[str, Any]] = {
            "happy": {
                "voice": default_voice,
                "speed": 1.1,
                "pitch": 0.2,
                "energy": 0.8,
            },
            "sad": {
                "voice": default_voice,
                "speed": 0.9,
                "pitch": -0.2,
                "energy": 0.4,
            },
            "angry": {
                "voice": default_voice,
                "speed": 1.2,
                "pitch": 0.3,
                "energy": 1.0,
            },
            "neutral": {
                "voice": default_voice,
                "speed": _STYLE_DEFAULT_SPEED,
                "pitch": _STYLE_DEFAULT_PITCH,
                "energy": 0.6,
            },
        }
        return table.get(emotion, table["neutral"])

    def _normalize_style(
        self, style: dict[str, Any], emotion: str
    ) -> dict[str, Any]:
        """规范化LLM输出的风格字段

        参数:
            style: LLM输出的风格字典
            emotion: 情绪标签（兜底用）

        返回:
            dict: 规范化后的风格配置
        """
        if not isinstance(style, dict):
            return self._fallback_style(emotion)
        fallback = self._fallback_style(emotion)
        voice = str(
            style.get("voice") or fallback["voice"]
        )
        try:
            speed = float(style.get("speed", fallback["speed"]))
        except (TypeError, ValueError):
            speed = fallback["speed"]
        try:
            pitch = float(style.get("pitch", fallback["pitch"]))
        except (TypeError, ValueError):
            pitch = fallback["pitch"]
        try:
            energy = float(style.get("energy", fallback["energy"]))
        except (TypeError, ValueError):
            energy = fallback["energy"]
        return {
            "voice": voice,
            "speed": max(0.5, min(2.0, speed)),
            "pitch": max(-1.0, min(1.0, pitch)),
            "energy": max(0.0, min(1.0, energy)),
        }

    async def clone_voice(
        self, sample_url: str, text: str
    ) -> bytes:
        """声音克隆接口（预留）

        根据声音样本URL克隆音色并合成指定文本。
        当前实现为预留接口，未接入实际克隆服务。

        参数:
            sample_url: 声音样本URL
            text: 待合成文本

        返回:
            bytes: 合成音频数据（当前返回空bytes）
        """
        logger.info(
            f"声音克隆接口被调用（预留）: sample={sample_url}",
            command="AI",
        )
        if not sample_url or not text:
            return b""
        if not self.check_safety(text):
            return b""
        return b""


enhanced_tts = EnhancedTTS()
"""增强TTS服务单例"""
