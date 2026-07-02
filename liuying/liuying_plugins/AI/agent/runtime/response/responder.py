"""角色化响应器

基于回合规划与证据合成结果，调用LLM生成最终回复。
按人格、用户画像、情绪状态调整输出，并产出结构化元信息
（情绪/语气/TTS风格/表情包情绪提示）供下游发送管线使用。
"""

from dataclasses import dataclass
import json
import re
import time
from typing import Any

from liuying.utils.log import logger

from ....core.llm import llm_helper
from ....core.persona import persona_manager
from ..constants import (
    OUTPUT_MODE_CHAT_ANSWER,
    OUTPUT_MODE_CHAT_SHORT,
    OUTPUT_MODE_SILENCE,
    OUTPUT_MODE_SOURCE_SUMMARY,
    OUTPUT_MODE_STRUCTURED_HELP,
)
from ..execution.evidence import EvidenceComposer
from ..planning.json_utils import extract_json_payload
from ..planning.types import TurnPlan

_RESPONDER_SYSTEM_PROMPT = """你是扮演角色化的响应器。
基于回合规划和收集到的证据，生成符合人格设定的回复。

输出要求：
1. 严格按JSON格式返回，字段如下：
   - reply_text: 回复正文
   - info_added: 是否补充了新信息（true/false）
   - user_attitude: 推测的用户态度（friendly/neutral/curious/upset/playful）
   - bot_emotion: 本回合AI情绪（happy/calm/excited/shy/sad/angry/neutral）
   - expression_style: 表达风格（casual/formal/playful/serious/gentle）
   - tts_style_hint: TTS风格提示（如温柔/活泼/严肃，留空表示不需要TTS）
   - sticker_mood_hint: 表情包情绪提示（如开心/害羞/无奈，留空表示不需要表情包）
   - ambiguity_level: 回复模糊度（0-1）
   - recommend_silence: 是否建议静默（true/false，仅当回复内容明显不需要发送时为true）

2. 回复风格要符合人格设定和用户好感度
3. 不要暴露工具调用细节和证据合成过程
4. 不要在回复中提及自己是AI助手
5. 回复要简洁自然，符合对话场景

只返回JSON，不要其他内容。"""

_RESPONDER_USER_TEMPLATE = """回合规划:
- 动作: {action}
- 输出模式: {output_mode}
- 意图标签: {intent_tags}
- 模糊度: {ambiguity_level}

证据合成:
{evidence_text}

证据指导:
{evidence_guidance}

用户消息: {user_message}

请输出角色化响应JSON。"""

_CLARIFY_TEMPLATES = (
    "嗯……能再说得详细一点吗？",
    "我没有完全理解，可以再解释一下吗？",
    "你是想问……吗？还是别的呢？",
)

_HELP_TEMPLATES = (
    "我可以陪你聊天、回答问题，也可以联网搜索信息、生成图片~",
    "需要我做什么呢？可以问我问题，让我搜索或者画画~",
)

_REPLY_TEXT_FALLBACK_PATTERN = re.compile(
    r'"reply_text"\s*:\s*"((?:\\.|[^"\\])*)"',
    re.IGNORECASE,
)
"""reply_text 兜底提取正则（支持JSON转义引号）"""

_STRING_FIELD_FALLBACK_PATTERNS: dict[str, re.Pattern] = {
    "user_attitude": re.compile(
        r'"user_attitude"\s*:\s*"?([^",}\n]+)"?',
        re.IGNORECASE,
    ),
    "bot_emotion": re.compile(
        r'"bot_emotion"\s*:\s*"?([^",}\n]+)"?',
        re.IGNORECASE,
    ),
    "expression_style": re.compile(
        r'"expression_style"\s*:\s*"?([^",}\n]+)"?',
        re.IGNORECASE,
    ),
    "tts_style_hint": re.compile(
        r'"tts_style_hint"\s*:\s*"((?:\\.|[^"\\])*)"',
        re.IGNORECASE,
    ),
    "sticker_mood_hint": re.compile(
        r'"sticker_mood_hint"\s*:\s*"((?:\\.|[^"\\])*)"',
        re.IGNORECASE,
    ),
}
"""字符串字段兜底提取正则"""

_BOOL_FIELD_FALLBACK_PATTERNS: dict[str, re.Pattern] = {
    "info_added": re.compile(
        r'"info_added"\s*:\s*(true|false)', re.IGNORECASE
    ),
    "recommend_silence": re.compile(
        r'"recommend_silence"\s*:\s*(true|false)', re.IGNORECASE
    ),
}
"""布尔字段兜底提取正则"""

_AMBIGUITY_FALLBACK_PATTERN = re.compile(
    r'"ambiguity_level"\s*:\s*([\d.]+)', re.IGNORECASE
)
"""模糊度字段兜底提取正则"""


@dataclass(slots=True)
class PersonaResponse:
    """角色化响应

    Attributes:
        reply_text: 回复正文
        info_added: 是否补充了新信息
        user_attitude: 推测的用户态度
        bot_emotion: AI情绪
        expression_style: 表达风格
        tts_style_hint: TTS风格提示
        sticker_mood_hint: 表情包情绪提示
        ambiguity_level: 回复模糊度
        recommend_silence: 是否建议静默
        elapsed: 生成耗时（秒）
        raw_response: LLM原始响应（调试用）
    """

    reply_text: str = ""
    info_added: bool = False
    user_attitude: str = "neutral"
    bot_emotion: str = "neutral"
    expression_style: str = "casual"
    tts_style_hint: str = ""
    sticker_mood_hint: str = ""
    ambiguity_level: float = 0.0
    recommend_silence: bool = False
    elapsed: float = 0.0
    raw_response: str = ""

    @property
    def is_silence(self) -> bool:
        """是否静默"""
        return self.recommend_silence or not self.reply_text.strip()

    def to_dict(self) -> dict[str, Any]:
        """转换为字典

        返回:
            dict: 响应字典
        """
        return {
            "reply_text": self.reply_text,
            "info_added": self.info_added,
            "user_attitude": self.user_attitude,
            "bot_emotion": self.bot_emotion,
            "expression_style": self.expression_style,
            "tts_style_hint": self.tts_style_hint,
            "sticker_mood_hint": self.sticker_mood_hint,
            "ambiguity_level": self.ambiguity_level,
            "recommend_silence": self.recommend_silence,
            "elapsed": round(self.elapsed, 3),
        }


class PersonaResponder:
    """角色化响应器

    整合规划、证据、人格信息，调用LLM生成结构化角色化响应。
    """

    def __init__(self, llm=None, persona_mgr=None) -> None:
        """初始化响应器

        参数:
            llm: LLM助手，None时使用模块单例
            persona_mgr: 人格管理器，None时使用模块单例
        """
        self._llm = llm
        self._persona_manager = persona_mgr

    def _get_llm(self):
        """获取LLM助手，None时回退到模块单例"""
        if self._llm is None:
            self._llm = llm_helper
        return self._llm

    def _get_persona_manager(self):
        """获取人格管理器，None时回退到模块单例"""
        if self._persona_manager is None:
            self._persona_manager = persona_manager
        return self._persona_manager

    async def respond(
        self,
        plan: TurnPlan,
        evidence: EvidenceComposer,
        user_message: str,
        messages: list[dict[str, str]] | None = None,
        user_id: str = "",
        group_id: str | None = None,
    ) -> PersonaResponse:
        """生成角色化响应

        参数:
            plan: 回合规划
            evidence: 证据合成器
            user_message: 用户消息
            messages: 对话历史（可选）
            user_id: 用户ID
            group_id: 群组ID

        返回:
            PersonaResponse: 角色化响应
        """
        start = time.time()

        # 静默
        if plan.is_silence:
            return PersonaResponse(
                reply_text="",
                recommend_silence=True,
                elapsed=time.time() - start,
                bot_emotion="neutral",
            )

        # 请求澄清：使用模板快速响应
        if plan.is_clarify:
            return PersonaResponse(
                reply_text=self._pick_clarify_template(user_message),
                bot_emotion="neutral",
                expression_style="gentle",
                ambiguity_level=plan.ambiguity_level,
                elapsed=time.time() - start,
            )

        # 结构化帮助：使用模板快速响应
        if plan.output_mode == OUTPUT_MODE_STRUCTURED_HELP:
            return PersonaResponse(
                reply_text=self._pick_help_template(user_message),
                bot_emotion="happy",
                expression_style="casual",
                sticker_mood_hint="开心",
                elapsed=time.time() - start,
            )

        # 基于LLM的响应生成
        try:
            response = await self._generate_via_llm(
                plan, evidence, user_message, messages, user_id, group_id
            )
            response.elapsed = time.time() - start
            return response
        except Exception as e:
            logger.warning(
                f"LLM响应生成失败，降级到证据文本: {e}",
                command="AI",
                e=e,
            )
            return self._fallback_response(plan, evidence, start)

    async def _generate_via_llm(
        self,
        plan: TurnPlan,
        evidence: EvidenceComposer,
        user_message: str,
        history: list[dict[str, str]] | None,
        user_id: str,
        group_id: str | None,
    ) -> PersonaResponse:
        """通过LLM生成响应

        参数:
            plan: 回合规划
            evidence: 证据合成器
            user_message: 用户消息
            history: 对话历史（不含本轮 user_message）
            user_id: 用户ID
            group_id: 群组ID

        返回:
            PersonaResponse: 角色化响应
        """
        llm = self._get_llm()

        evidence_text = evidence.compose(max_items=5)
        if not evidence_text:
            evidence_text = "（无工具证据）"

        evidence_guidance = evidence.build_evidence_guidance()
        if not evidence_guidance:
            evidence_guidance = "（无证据指导）"

        prompt = _RESPONDER_USER_TEMPLATE.format(
            action=plan.action,
            output_mode=plan.output_mode,
            intent_tags=", ".join(plan.intent_tags) or "（无）",
            ambiguity_level=round(plan.ambiguity_level, 2),
            evidence_text=evidence_text,
            evidence_guidance=evidence_guidance,
            user_message=user_message[:500],
        )

        # 构建系统提示词（含人格与用户画像）
        system_prompt = await self._build_system_prompt(
            user_id, group_id, plan.output_mode
        )

        # 构建消息列表：系统提示 + 规划指令 + 对话历史 + 当前回合请求
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": _RESPONDER_SYSTEM_PROMPT},
        ]
        if history:
            # 仅保留最近 6 条历史，避免 token 膨胀
            recent = history[-6:]
            for msg in recent:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append(
                        {"role": role, "content": content[:500]}
                    )
        messages.append({"role": "user", "content": prompt})

        _, response_text = await llm.chat(
            messages, options={"temperature": 0.7}
        )
        return self._parse_response(response_text, plan)

    async def _build_system_prompt(
        self,
        user_id: str,
        group_id: str | None,
        output_mode: str,
    ) -> str:
        """构建系统提示词

        参数:
            user_id: 用户ID
            group_id: 群组ID
            output_mode: 输出模式

        返回:
            str: 系统提示词
        """
        try:
            persona_mgr = self._get_persona_manager()
            persona = await persona_mgr.get_user_persona_config(
                user_id
            )
            persona_prompt = await persona_mgr.build_system_prompt(
                persona, user_id, group_id
            )
        except Exception as e:
            logger.debug(
                f"加载人格失败，使用默认: {e}", command="AI"
            )
            persona_prompt = "你是流萤，一个温柔、有活力的AI伙伴。"

        mode_hint = self._get_mode_hint(output_mode)
        return f"{persona_prompt}\n\n{mode_hint}"

    def _get_mode_hint(self, output_mode: str) -> str:
        """根据输出模式获取提示

        参数:
            output_mode: 输出模式

        返回:
            str: 模式提示
        """
        hints = {
            OUTPUT_MODE_CHAT_SHORT: "本回合是短聊天回复，保持简洁自然。",
            OUTPUT_MODE_CHAT_ANSWER: "本回合是完整答案回复，需详细但有条理。",
            OUTPUT_MODE_SOURCE_SUMMARY: (
                "本回合带工具证据，请自然地融入证据信息，"
                "不要直接说'根据搜索结果'等。"
            ),
            OUTPUT_MODE_SILENCE: "本回合建议静默。",
        }
        return hints.get(output_mode, "")

    def _parse_response(
        self, response: str, plan: TurnPlan
    ) -> PersonaResponse:
        """解析LLM响应

        使用 extract_json_payload 四重兜底提取JSON：
        1. 直接 json.loads
        2. 去除 markdown fence 后再解析
        3. 修复未加引号的枚举值后再解析
        4. 正则提取首个 {...} 块再解析

        JSON解析失败时，调用 _parse_response_fallback 进行正则兜底
        提取，优先取 reply_text 字段，避免把原始JSON块直接输出。

        参数:
            response: LLM响应文本
            plan: 回合规划

        返回:
            PersonaResponse: 解析后的响应
        """
        raw = response.strip()
        data = extract_json_payload(response)

        if data is None:
            return self._parse_response_fallback(raw, plan)

        reply_text = str(
            data.get("reply_text", data.get("replytext", ""))
        ).strip()
        if not reply_text:
            reply_text = raw

        ambiguity = float(
            data.get("ambiguity_level", data.get("ambiguitylevel", 0.0))
        )
        ambiguity = max(0.0, min(1.0, ambiguity))

        return PersonaResponse(
            reply_text=reply_text,
            info_added=bool(
                data.get("info_added", data.get("infoadded", False))
            ),
            user_attitude=str(
                data.get("user_attitude", data.get("userattitude", "neutral"))
            ),
            bot_emotion=str(
                data.get("bot_emotion", data.get("botemotion", "neutral"))
            ),
            expression_style=str(
                data.get(
                    "expression_style",
                    data.get("expressionstyle", "casual"),
                )
            ),
            tts_style_hint=str(
                data.get("tts_style_hint", data.get("ttsstylehint", ""))
            ),
            sticker_mood_hint=str(
                data.get(
                    "sticker_mood_hint",
                    data.get("stickermoodhint", ""),
                )
            ),
            ambiguity_level=ambiguity,
            recommend_silence=bool(
                data.get(
                    "recommend_silence",
                    data.get("recommendsilence", False),
                )
            ),
            raw_response=raw,
        )

    def _parse_response_fallback(
        self, raw: str, plan: TurnPlan
    ) -> PersonaResponse:
        """JSON解析失败时的兜底解析

        当 extract_json_payload 无法解析完整JSON时，尝试用正则
        提取 reply_text 等关键字段，避免把原始JSON块直接输出。
        如果正则也无法提取 reply_text，才回退到原始文本。

        参数:
            raw: LLM原始响应
            plan: 回合规划

        返回:
            PersonaResponse: 兜底响应
        """
        reply_text = ""
        match = _REPLY_TEXT_FALLBACK_PATTERN.search(raw)
        if match:
            captured = match.group(1)
            try:
                reply_text = json.loads(f'"{captured}"')
            except json.JSONDecodeError:
                reply_text = captured
            reply_text = reply_text.strip()

        if not reply_text:
            reply_text = raw

        string_fields: dict[str, str] = {}
        for name, pattern in _STRING_FIELD_FALLBACK_PATTERNS.items():
            m = pattern.search(raw)
            string_fields[name] = m.group(1).strip() if m else ""

        bool_fields: dict[str, bool] = {}
        for name, pattern in _BOOL_FIELD_FALLBACK_PATTERNS.items():
            m = pattern.search(raw)
            bool_fields[name] = m.group(1).lower() == "true" if m else False

        ambiguity_match = _AMBIGUITY_FALLBACK_PATTERN.search(raw)
        if ambiguity_match:
            try:
                ambiguity = float(ambiguity_match.group(1))
                ambiguity = max(0.0, min(1.0, ambiguity))
            except (TypeError, ValueError):
                ambiguity = plan.ambiguity_level
        else:
            ambiguity = plan.ambiguity_level

        return PersonaResponse(
            reply_text=reply_text,
            info_added=bool_fields.get("info_added", False),
            user_attitude=string_fields.get("user_attitude", "neutral"),
            bot_emotion=string_fields.get("bot_emotion", "neutral"),
            expression_style=string_fields.get(
                "expression_style", "casual"
            ),
            tts_style_hint=string_fields.get("tts_style_hint", ""),
            sticker_mood_hint=string_fields.get(
                "sticker_mood_hint", ""
            ),
            ambiguity_level=ambiguity,
            recommend_silence=bool_fields.get(
                "recommend_silence", False
            ),
            raw_response=raw,
        )

    def _pick_clarify_template(self, user_message: str) -> str:
        """选择澄清回复模板

        参数:
            user_message: 用户消息

        返回:
            str: 澄清回复
        """
        text = user_message.lower()
        if "?" in user_message or "？" in user_message:
            return _CLARIFY_TEMPLATES[0]
        if any(kw in text for kw in ("怎么", "如何", "为什么")):
            return _CLARIFY_TEMPLATES[1]
        return _CLARIFY_TEMPLATES[2]

    def _pick_help_template(self, user_message: str) -> str:
        """选择帮助回复模板

        参数:
            user_message: 用户消息

        返回:
            str: 帮助回复
        """
        text = user_message.lower()
        if any(kw in text for kw in ("搜索", "联网", "查")):
            return _HELP_TEMPLATES[1]
        return _HELP_TEMPLATES[0]

    def _fallback_response(
        self,
        plan: TurnPlan,
        evidence: EvidenceComposer,
        start: float,
    ) -> PersonaResponse:
        """降级响应（LLM失败时）

        参数:
            plan: 回合规划
            evidence: 证据合成器
            start: 开始时间

        返回:
            PersonaResponse: 降级响应
        """
        evidence_text = evidence.compose(max_items=3)
        if evidence_text:
            reply = "我查到了一些信息，但回复生成遇到点问题，待会再试试~"
        else:
            reply = "嗯……出了点小问题，待会再聊~"

        return PersonaResponse(
            reply_text=reply,
            bot_emotion="neutral",
            expression_style="casual",
            ambiguity_level=plan.ambiguity_level,
            elapsed=time.time() - start,
        )
