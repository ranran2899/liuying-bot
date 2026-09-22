"""主模型人格回复阶段（ROLE_CHAT 受约束生成）

从统一 ReAct 循环中剥离出"写正文"这一步：工具编排阶段只产出证据
与收束元信息，最终正文始终由主模型（ROLE_CHAT）的一次干净人格 pass
生成。本模块复刻旧响应器的受约束生成以保住拟人化——抽取人格系统提示词、
把历史压缩为最近若干条、将用户这句话单独置于末尾作为待回复目标，并在
用户轮末尾重申"回复模式"以就近锁定详略；正文以只含 reply_text 的 JSON
产出。情绪/静默等元信息由编排阶段的 finish 工具给出，此处不再涉及工具框架。
"""

import json
import re
from typing import Any

from liuying.utils.log import logger

from ...core.llm import LLMHelper, llm_helper
from ...core.llm.model_router import ROLE_CHAT, model_router
from ...core.tools.json_utils import extract_json_payload
from .constants import IMAGE_OUTPUT_KIND
from .types import PersonaResponse, ToolCallRecord

_EMPTY_RESULT_MARKERS: tuple[str, ...] = (
    "未找到",
    "没有找到",
    "无结果",
    "暂无",
    "未检索到",
    "搜索失败",
)
"""空结果文本标记，命中的工具结果不作为证据喂给回复阶段"""

_REPLY_TEXT_PATTERN = re.compile(
    r'"reply_text"\s*:\s*"((?:\\.|[^"\\])*)"', re.IGNORECASE
)
"""compose 产出非标准JSON时兜底提取 reply_text 字段"""


class ReplyComposer:
    """主模型人格回复生成器

    职责单一：把完整消息、工具证据与编排阶段的收束元信息喂给 ROLE_CHAT，
    受约束地生成符合人格的最终正文。
    """

    def __init__(self, llm: LLMHelper | None = None) -> None:
        """初始化生成器

        参数:
            llm: LLM助手，None时用单例
        """
        self._llm = llm or llm_helper

    async def compose(
        self,
        messages: list[dict[str, Any]],
        records: list[ToolCallRecord],
        meta: dict[str, Any],
    ) -> PersonaResponse:
        """人格回复阶段：用主模型(ROLE_CHAT)受约束地写最终正文

        参数:
            messages: 完整消息列表（[system人格, *历史, 用户]）
            records: 工具阶段的成功记录（作为证据）
            meta: finish 阶段给出的情绪/静默/澄清/TTS/贴纸/详略/要点

        返回:
            PersonaResponse: 含正文与元信息的角色化响应
        """
        role_chat = model_router.resolve(ROLE_CHAT)
        system_prompt = self._extract_system_prompt(messages)
        evidence = self._render_evidence(records)
        user_message = self._extract_last_user_message(messages)
        min_chars, max_chars = self._reply_budget(bool(evidence))
        combined_system = (
            f"{system_prompt}\n\n"
            f"{self._reply_instruction(min_chars, max_chars, bool(evidence))}"
        )
        reply_messages: list[dict[str, Any]] = [
            {"role": "system", "content": combined_system}
        ]
        for msg in self._extract_chat_history(messages)[-4:]:
            text = _flatten_content(msg.get("content", ""))
            if text:
                reply_messages.append(
                    {
                        "role": str(msg.get("role")),
                        "content": text[:200],
                    }
                )
        user_parts: list[str] = [
            f"回复模式：{self._mode_hint(bool(evidence))}"
        ]
        if evidence:
            user_parts.append(f"证据摘要：\n{evidence}")
        key_points = str(meta.get("key_points") or "").strip()
        if key_points:
            user_parts.append(f"编排要点（内部参考，勿照搬）：{key_points}")
        user_parts.append(f"用户消息：{user_message[:500]}")
        user_parts.append("请输出角色化响应JSON。")
        reply_messages.append(
            {"role": "user", "content": "\n\n".join(user_parts)}
        )
        try:
            _, content = await self._llm.chat(
                reply_messages,
                model=role_chat.model or None,
                options=role_chat.apply_to_options({"max_tokens": 2048}),
                provider_name=role_chat.provider or None,
            )
        except Exception as e:
            logger.error(
                f"人格回复阶段LLM调用失败: {e}", command="AI", e=e
            )
            content = ""
        return self._parse_compose(content, meta)

    @staticmethod
    def _render_evidence(
        records: list[ToolCallRecord],
    ) -> str:
        """将工具成功结果渲染为证据块（供主模型参考）

        跳过失败与空结果；图片生成结果用占位描述替代，避免模型
        把图片 URL 念进正文。

        参数:
            records: 工具调用记录

        返回:
            str: 证据文本，无有效结果时返回空串
        """
        lines: list[str] = []
        for r in records:
            if not r.success:
                continue
            text = r.result.strip()
            if not text or any(m in text for m in _EMPTY_RESULT_MARKERS):
                continue
            if r.metadata.get("output_kind") == IMAGE_OUTPUT_KIND:
                text = "已生成图片，将以图片消息形式发送"
            lines.append(f"[{r.tool_name}] {text[:200]}")
        if not lines:
            return ""
        return (
            "[本轮工具已查证到的信息，请自然融入回复，不要照搬原文、"
            "不要提及工具或来源]\n" + "\n".join(lines)
        )

    @staticmethod
    def _extract_system_prompt(
        messages: list[dict[str, Any]],
    ) -> str:
        """提取首个非空 system 内容（人格 + 已注入的风格/工具指导）

        参数:
            messages: 完整消息列表

        返回:
            str: 系统提示词，缺失时返回空串
        """
        for msg in messages:
            if msg.get("role") == "system" and msg.get("content"):
                return str(msg["content"])
        return ""

    @staticmethod
    def _extract_last_user_message(
        messages: list[dict[str, Any]],
    ) -> str:
        """提取最后一条 user 消息文本（当前待回复消息）

        参数:
            messages: 完整消息列表

        返回:
            str: 用户消息文本，多模态时拼接其 text 片段
        """
        for msg in reversed(messages):
            if msg.get("role") == "user":
                return _flatten_content(msg.get("content", ""))
        return ""

    @staticmethod
    def _extract_chat_history(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """提取对话历史（仅 user/assistant，排除当前用户消息）

        参数:
            messages: 完整消息列表

        返回:
            list[dict]: 按时间正序的历史消息（末条当前消息已剔除）
        """
        history = [
            msg
            for msg in messages
            if msg.get("role") in ("user", "assistant")
        ]
        if history:
            history.pop()
        return history

    @staticmethod
    def _reply_budget(has_evidence: bool) -> tuple[int, int]:
        """回复字数预算：无工具证据按闲聊短句，有证据放宽到说明型

        复刻旧 planner 的 chat_short/chat_answer 长度控制。不再让
        编排模型自选详略档（便宜模型常把闲聊误判成正常回答放宽到
        120 字，导致堆砌背景设定的废话）。

        参数:
            has_evidence: 本轮是否有工具证据

        返回:
            tuple[int, int]: (最小字数, 最大字数)
        """
        return (30, 120) if has_evidence else (8, 40)

    @staticmethod
    def _reply_instruction(
        min_chars: int, max_chars: int, need_tool: bool
    ) -> str:
        """回复阶段指令（沿用旧 responder.py 的角色文案与约束清单）

        直接抄用旧响应器的约束与字数硬约束，仅把输出格式保持为只含
        reply_text 的 JSON——是否静默/澄清/情绪等元信息已由编排阶段的
        finish 工具给出，正文无需其他字段。

        参数:
            min_chars: 字数下限
            max_chars: 字数上限
            need_tool: 本轮是否已用工具查证（否则追加禁编造硬约束）

        返回:
            str: 回复生成指令
        """
        constraints = [
            "1. 回复风格符合人格设定和用户好感度",
            "2. 不暴露工具调用细节和证据合成过程",
            "3. 不提及自己是AI助手",
            "4. 回复简洁自然，符合对话场景",
            "5. 不编造具体数字、链接、日期",
            "6. 未调用工具且不确定时，用简短模糊回应，禁止编造",
            "7. 不要每轮都用反问或提问收尾，别连环问；"
            "多数时候用陈述自然接话",
        ]
        if not need_tool:
            constraints.append(
                "8. 涉及具体事实/数字/时间/人名/新闻/产品参数/专有名词/"
                "梗，未调用工具且不确定时必须简短含糊回应，禁止编造"
            )
        return (
            "你是角色化响应器。基于人格设定和证据，生成符合角色的回复。\n"
            '只输出一个JSON对象：{"reply_text": "回复正文"}，'
            "不要其他字段、解释、markdown或代码块。\n\n"
            f"字数约束：reply_text必须在{min_chars}-{max_chars}字之间。\n\n"
            "约束：\n" + "\n".join(constraints)
        )

    @staticmethod
    def _mode_hint(has_evidence: bool) -> str:
        """就近的回复模式提示（复刻旧 responder 的 mode_hint）

        参数:
            has_evidence: 本轮是否有工具证据

        返回:
            str: 模式提示文本
        """
        if has_evidence:
            return "带工具证据，自然融入证据，不要说'根据搜索结果'"
        return (
            "短聊天回复，只回一到两句；用户没问就别自我介绍、"
            "不要罗列人设设定里的爱好或背景，也别总用反问收尾"
        )

    @staticmethod
    def _parse_compose(
        raw: str, meta: dict[str, Any]
    ) -> PersonaResponse:
        """解析回复阶段的 JSON 产出，兜底提取正文

        参数:
            raw: 主模型原始输出
            meta: finish 阶段的静默/澄清/情绪/TTS/贴纸提示

        返回:
            PersonaResponse: 角色化响应
        """
        text = raw.strip()
        data = extract_json_payload(raw)
        if data is not None:
            text = str(data.get("reply_text", "")).strip() or text
        else:
            match = _REPLY_TEXT_PATTERN.search(raw)
            if match:
                try:
                    text = json.loads(f'"{match.group(1)}"')
                except json.JSONDecodeError:
                    text = match.group(1)
        return PersonaResponse(
            reply_text=text.strip(),
            recommend_silence=bool(meta.get("recommend_silence", False)),
            ask_clarify=bool(meta.get("ask_clarify", False)),
            bot_emotion=str(meta.get("bot_emotion") or "neutral"),
            tts_style_hint=str(meta.get("tts_style_hint", "")),
            sticker_mood_hint=str(meta.get("sticker_mood_hint", "")),
            raw_response=raw,
        )


def _flatten_content(raw: Any) -> str:
    """把消息 content 归一化为纯文本

    兼容字符串与多模态片段列表（OpenAI content parts），后者
    仅拼接其中的 text 片段，供回复阶段压缩历史/提取用户消息使用。

    参数:
        raw: 消息 content（str 或 list[dict]）

    返回:
        str: 拼接后的文本，无文本时返回空串
    """
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        return "".join(
            part.get("text", "")
            for part in raw
            if isinstance(part, dict)
        )
    return str(raw or "")
