"""聊天意图语义帧

通过LLM推断回合级语义帧，提供比关键词匹配更细粒度的决策信号。
包含15+维度的语义字段，覆盖意图/情绪/态度/场景/表达风格等。

语义帧作为规划器的增强信号，与现有 intent_rules 关键词规则协同：
- 关键词规则：低延迟快速决策路径
- LLM语义帧：精细决策路径，补充情绪/态度/贴纸适配等维度
"""

from dataclasses import dataclass
from typing import Any

from liuying.utils.log import logger

from .json_utils import extract_json_payload
from .llm import LLMHelper, llm_helper
from .llm.model_router import ROLE_INTENT, model_router

__all__ = [
    "SemanticFrameInferrer",
    "TurnSemanticFrame",
    "semantic_frame_inferrer",
]


_FRAME_SYSTEM_PROMPT = """你是聊天意图语义分析器。
分析用户消息和上下文，输出回合级语义帧JSON。

字段说明：
- chat_intent: 聊天意图
  （question/small_talk/info_seek/emotional_support/
  social_protocol/chat_command/meta_question）
- plugin_question_intent: 插件相关意图（空串表示无）
- ambiguity_level: 模糊度（0-1，0最清晰）
- recommend_silence: 是否建议静默（true/false）
- requires_emotional_care: 是否需要情感关怀（true/false）
- sticker_appropriate: 是否适合发贴纸（true/false）
- meta_question: 是否元问题（关于bot自身，true/false）
- domain_focus: 领域焦点（空串表示无）
- user_attitude: 用户态度（positive/neutral/negative/playful）
- bot_emotion: bot应有情绪
  （happy/sad/neutral/curious/caring/playful）
- emotion_intensity: 情绪强度（0-1）
- expression_style: 表达风格（casual/formal/playful/gentle）
- tts_style_hint: TTS风格提示（空串表示无）
- sticker_mood_hint: 贴纸情绪提示（warm/cool/neutral）
- conversation_scenario: 对话场景
  （daily/greeting/farewell/help/conflict/tease）

只返回JSON，不要其他内容。"""


_FRAME_USER_TEMPLATE = """用户消息: {user_message}

上下文摘要: {context_summary}

请输出语义帧JSON。"""


@dataclass(slots=True)
class TurnSemanticFrame:
    """回合语义帧

    描述当前回合的多维度语义信息，由LLM推断或规则快速生成。

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
    """语义帧推断器

    封装LLM语义帧推断与规则快速推断两种模式。
    LLM模式提供15+维度精细分析，规则模式提供基础降级。
    """

    def __init__(self, llm: LLMHelper | None = None) -> None:
        """初始化语义帧推断器

        参数:
            llm: LLM助手，None时使用模块单例
        """
        self._llm = llm

    def _get_llm(self) -> LLMHelper:
        """获取LLM助手，None时回退到模块单例"""
        if self._llm is None:
            self._llm = llm_helper
        return self._llm

    async def infer(
        self,
        user_message: str,
        context_summary: str = "",
        use_llm: bool = True,
    ) -> TurnSemanticFrame:
        """推断语义帧

        参数:
            user_message: 用户消息
            context_summary: 上下文摘要
            use_llm: 是否使用LLM精细推断，False时用规则快速推断

        返回:
            TurnSemanticFrame: 语义帧
        """
        if not use_llm:
            return self.infer_fast(user_message)
        prompt = _FRAME_USER_TEMPLATE.format(
            user_message=user_message[:500],
            context_summary=context_summary[:300] or "（无）",
        )
        try:
            llm = self._get_llm()
            role = model_router.resolve(ROLE_INTENT)
            _, response = await llm.chat(
                [
                    {"role": "system", "content": _FRAME_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                model=role.model or None,
                options=role.apply_to_options(),
                provider_name=role.provider or None,
            )
            frame = self._parse_frame_response(response)
            return frame
        except Exception as e:
            logger.warning(
                f"LLM语义帧推断失败，降级到规则: {e}",
                command="AI",
                e=e,
            )
            return self.infer_fast(user_message)

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

    def _parse_frame_response(
        self, response: str
    ) -> TurnSemanticFrame:
        """解析LLM语义帧响应

        参数:
            response: LLM响应文本

        返回:
            TurnSemanticFrame: 解析后的语义帧
        """
        data = extract_json_payload(response)
        if data is None:
            logger.debug(
                "解析语义帧JSON失败，降级到规则",
                command="AI",
            )
            return self.infer_fast("")

        def _clamp01(value: Any) -> float:
            """将值限制在0-1范围"""
            if isinstance(value, int | float) and not isinstance(
                value, bool
            ):
                return max(0.0, min(1.0, float(value)))
            return 0.0

        return TurnSemanticFrame(
            chat_intent=str(data.get("chat_intent", "small_talk")),
            plugin_question_intent=str(
                data.get("plugin_question_intent", "")
            ),
            ambiguity_level=_clamp01(
                data.get("ambiguity_level", 0.0)
            ),
            recommend_silence=bool(
                data.get("recommend_silence", False)
            ),
            requires_emotional_care=bool(
                data.get("requires_emotional_care", False)
            ),
            sticker_appropriate=bool(
                data.get("sticker_appropriate", False)
            ),
            meta_question=bool(data.get("meta_question", False)),
            domain_focus=str(data.get("domain_focus", "")),
            user_attitude=str(data.get("user_attitude", "neutral")),
            bot_emotion=str(data.get("bot_emotion", "neutral")),
            emotion_intensity=_clamp01(
                data.get("emotion_intensity", 0.0)
            ),
            expression_style=str(
                data.get("expression_style", "casual")
            ),
            tts_style_hint=str(data.get("tts_style_hint", "")),
            sticker_mood_hint=str(
                data.get("sticker_mood_hint", "neutral")
            ),
            conversation_scenario=str(
                data.get("conversation_scenario", "daily")
            ),
        )


semantic_frame_inferrer = SemanticFrameInferrer()
"""语义帧推断器单例"""
