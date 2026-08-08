"""聊天意图语义帧

提供基于关键词规则的回合级语义帧快速推断，作为规划器的
降级路径。LLM精细语义帧已内嵌到规划器的单次LLM调用中，
本模块仅保留规则快速推断（infer_fast），消除冗余LLM调用。
"""

from dataclasses import dataclass
from typing import Any

__all__ = [
    "SemanticFrameInferrer",
    "TurnSemanticFrame",
    "semantic_frame_inferrer",
]


@dataclass(slots=True)
class TurnSemanticFrame:
    """回合语义帧

    描述当前回合的多维度语义信息，由规则快速生成。

    Attributes:
        chat_intent: 聊天意图
        plugin_question_intent: 插件相关意图
        ambiguity_level: 模糊度（0-1）
        recommend_silence: 是否建议静默
        requires_emotional_care: 是否需要情感关怀
        sticker_appropriate: 是否适合发贴纸
        meta_question: 是否元问题
        domain_focus: 领域焦点
        user_attitude: 用户态度
        bot_emotion: bot应有情绪
        emotion_intensity: 情绪强度（0-1）
        expression_style: 表达风格
        tts_style_hint: TTS风格提示
        sticker_mood_hint: 贴纸情绪提示
        conversation_scenario: 对话场景
    """

    chat_intent: str = "small_talk"
    plugin_question_intent: str = ""
    ambiguity_level: float = 0.0
    recommend_silence: bool = False
    requires_emotional_care: bool = False
    sticker_appropriate: bool = False
    meta_question: bool = False
    domain_focus: str = ""
    user_attitude: str = "neutral"
    bot_emotion: str = "neutral"
    emotion_intensity: float = 0.0
    expression_style: str = "casual"
    tts_style_hint: str = ""
    sticker_mood_hint: str = "neutral"
    conversation_scenario: str = "daily"

    def to_dict(self) -> dict[str, Any]:
        """转换为字典

        返回:
            dict: 语义帧字典
        """
        return {
            "chat_intent": self.chat_intent,
            "plugin_question_intent": self.plugin_question_intent,
            "ambiguity_level": self.ambiguity_level,
            "recommend_silence": self.recommend_silence,
            "requires_emotional_care": self.requires_emotional_care,
            "sticker_appropriate": self.sticker_appropriate,
            "meta_question": self.meta_question,
            "domain_focus": self.domain_focus,
            "user_attitude": self.user_attitude,
            "bot_emotion": self.bot_emotion,
            "emotion_intensity": self.emotion_intensity,
            "expression_style": self.expression_style,
            "tts_style_hint": self.tts_style_hint,
            "sticker_mood_hint": self.sticker_mood_hint,
            "conversation_scenario": self.conversation_scenario,
        }


class SemanticFrameInferrer:
    """语义帧规则推断器

    基于关键词匹配推断基础语义字段，作为规划器LLM降级路径。
    LLM精细语义帧已内嵌到规划器的单次调用中，本模块不再
    发起独立LLM调用。
    """

    def infer_fast(self, user_message: str) -> TurnSemanticFrame:
        """规则快速推断语义帧（无LLM调用）

        基于关键词匹配推断基础语义字段，作为LLM降级路径。

        参数:
            user_message: 用户消息

        返回:
            TurnSemanticFrame: 语义帧
        """
        text = user_message.strip().lower()
        if not text:
            return TurnSemanticFrame(
                chat_intent="small_talk",
                recommend_silence=True,
                conversation_scenario="daily",
            )

        if any(kw in text for kw in ["你好", "早", "晚上好", "嗨", "hi"]):
            return TurnSemanticFrame(
                chat_intent="small_talk",
                conversation_scenario="greeting",
                sticker_appropriate=True,
                bot_emotion="happy",
                emotion_intensity=0.5,
                sticker_mood_hint="warm",
            )
        if any(kw in text for kw in ["再见", "拜拜", "晚安", "走了"]):
            return TurnSemanticFrame(
                chat_intent="social_protocol",
                conversation_scenario="farewell",
                sticker_appropriate=True,
                bot_emotion="sad",
                emotion_intensity=0.3,
                sticker_mood_hint="warm",
            )
        if any(kw in text for kw in ["谢谢", "感谢", "多谢"]):
            return TurnSemanticFrame(
                chat_intent="social_protocol",
                user_attitude="positive",
                bot_emotion="happy",
                emotion_intensity=0.5,
                sticker_mood_hint="warm",
            )
        if any(kw in text for kw in ["难过", "伤心", "崩溃", "累了", "烦"]):
            return TurnSemanticFrame(
                chat_intent="emotional_support",
                requires_emotional_care=True,
                user_attitude="negative",
                bot_emotion="caring",
                emotion_intensity=0.7,
                expression_style="gentle",
                sticker_mood_hint="warm",
            )
        if any(kw in text for kw in ["你是谁", "你叫什么", "你会什么"]):
            return TurnSemanticFrame(
                chat_intent="meta_question",
                meta_question=True,
                conversation_scenario="help",
            )
        if any(kw in text for kw in ["帮助", "怎么用", "命令"]):
            return TurnSemanticFrame(
                chat_intent="info_seek",
                conversation_scenario="help",
            )
        if "?" in text or "？" in text:
            return TurnSemanticFrame(
                chat_intent="question",
                bot_emotion="curious",
                emotion_intensity=0.3,
            )
        return TurnSemanticFrame(
            chat_intent="small_talk",
            conversation_scenario="daily",
            sticker_appropriate=True,
        )


semantic_frame_inferrer = SemanticFrameInferrer()
"""语义帧推断器单例"""
