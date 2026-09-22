"""统一 ReAct Agent 循环（工具编排 + 主模型人格回复两阶段）

以 ReAct 闭环驱动"推理 -> 原生 function-calling 调用工具 -> 观察结果
-> 再决策"，但把"工具编排"与"写正文"解耦：

- 工具编排阶段用 ROLE_AGENT（可为便宜模型），只负责判断/调用工具与
  收束判断（是否静默/澄清、情绪/TTS/贴纸提示），通过 ``finish`` 元工具结束；
- 正文一律由 ROLE_CHAT（主模型）的一次干净人格 pass 生成（_compose_reply），
  喂入人格提示词 + 对话历史 + 工具证据，不携带任何 agent/工具框架指令，
  以保证拟人化语气——这是拟人化的核心。

工具执行保留参数校验、超时、会话上下文绑定，异常以观察文本回灌供模
型自我纠错；HTTP 全失败时 chat_tools 降级为直答，人格 pass 仍会兼底生成。
"""

import asyncio
from dataclasses import dataclass, field
import json
import re
import time
from typing import Any

from liuying.utils.log import logger

from ...config import get_config
from ...core.llm import LLMHelper, llm_helper
from ...core.llm.model_router import ROLE_AGENT, ROLE_CHAT, model_router
from ...core.tools.json_utils import extract_json_payload
from ...pipeline.style_policy import (
    CROSSTALK_GUARD_PROMPT,
    CROSSTALK_MARKER,
    TOOL_GUIDANCE_PROMPT,
)
from ...tools import ToolRegistry, tool_registry
from .constants import DEFAULT_TOOL_TIMEOUT
from .session_context import bind_session_context

TOOL_FINISH = "finish"
"""收束元工具名：工具编排阶段调用它结束本回合（不写正文）"""

_DEFAULT_MAX_STEPS = 6
"""默认最大循环步数（每步一次 LLM 往返 + 若干工具调用）"""

_IMAGE_OUTPUT_KIND = "image_url"
"""图片生成类工具的产出标记"""

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

_FINISH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": TOOL_FINISH,
        "description": (
            "结束工具编排阶段。当你已掌握足够信息、或判断应静默/"
            "需澄清时调用它。不要在此写面向用户的正文，正文由后续的"
            "人格回复阶段生成；这里只需给出是否静默/是否澄清与情绪/TTS/"
            "贴纸等提示。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "recommend_silence": {
                    "type": "boolean",
                    "description": "是否建议静默不回复（仅群聊背景闲聊）",
                },
                "ask_clarify": {
                    "type": "boolean",
                    "description": "是否需要向用户澄清",
                },
                "bot_emotion": {
                    "type": "string",
                    "description": "本轮 bot 情绪（happy/calm/shy/sad/angry/neutral）",
                },
                "tts_style_hint": {
                    "type": "string",
                    "description": "TTS 语气提示（可空）",
                },
                "sticker_mood_hint": {
                    "type": "string",
                    "description": "贴纸/表情包情绪提示（可空）",
                },
                "key_points": {
                    "type": "string",
                    "description": (
                        "供回复阶段参考的要点/结论（内部用，可空）："
                        "跨工具查证后的结论性信息，用简短要点，勿写成整句回复"
                    ),
                },
            },
            "required": [],
        },
    },
}


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
        ask_clarify: 是否需要澄清
        elapsed: 生成耗时（秒）
        raw_response: 原始回复文本（调试用）
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
    ask_clarify: bool = False
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
            "ask_clarify": self.ask_clarify,
            "elapsed": round(self.elapsed, 3),
        }


@dataclass(slots=True)
class ToolCallRecord:
    """工具调用记录

    Attributes:
        tool_name: 工具名
        args: 调用参数
        result: 调用结果
        elapsed: 耗时（秒）
        success: 是否成功
        error: 错误信息（失败时）
        timestamp: 调用时间戳
        metadata: 工具元数据
    """

    tool_name: str
    args: dict[str, Any] = field(default_factory=dict)
    result: str = ""
    elapsed: float = 0.0
    success: bool = False
    error: str = ""
    timestamp: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典

        返回:
            dict: 调用记录字典
        """
        return {
            "tool_name": self.tool_name,
            "args": dict(self.args),
            "result": self.result[:500],
            "elapsed": round(self.elapsed, 3),
            "success": self.success,
            "error": self.error,
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class AgentOutcome:
    """Agent 循环产出

    Attributes:
        response: 角色化响应
        tool_calls: 工具调用记录列表
        steps: 实际执行步数
        metrics: 执行指标
        image_url: 生成的图片URL，None表示无图片
        elapsed: 总耗时（秒）
    """

    response: PersonaResponse
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    steps: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)
    image_url: str | None = None
    elapsed: float = 0.0


class AgentLoop:
    """统一 ReAct 循环执行器"""

    def __init__(
        self,
        llm: LLMHelper | None = None,
        registry: ToolRegistry | None = None,
    ) -> None:
        """初始化循环

        参数:
            llm: LLM助手，None时用单例
            registry: 工具注册表，None时用单例
        """
        self._llm = llm or llm_helper
        self._registry = registry or tool_registry

    async def run(
        self,
        messages: list[dict[str, Any]],
        user_id: str = "",
        group_id: str | None = None,
        persona_name: str = "default",
        is_at_bot: bool = False,
        max_steps: int | None = None,
        time_budget: float | None = None,
    ) -> AgentOutcome:
        """执行 ReAct 循环

        参数:
            messages: 完整消息列表（含 system 提示词与对话历史，末条为用户消息）
            user_id: 用户ID（工具经会话上下文读取）
            group_id: 群组ID
            persona_name: bot人格名
            is_at_bot: 消息是否直达bot（私聊/@bot/回复bot）
            max_steps: 最大步数，None时用配置或默认
            time_budget: 总时间预算（秒），None时用配置或默认

        返回:
            AgentOutcome: 循环产出
        """
        start = time.time()
        if not messages:
            return AgentOutcome(response=PersonaResponse(), elapsed=0.0)

        budget = (
            time_budget
            if time_budget is not None
            else float(get_config("AGENT", {}).get("response_timeout", 180))
        )
        steps_cap = max_steps or int(
            get_config("AGENT", {}).get("max_steps", _DEFAULT_MAX_STEPS)
        )

        # 工具编排阶段：循环模型(ROLE_AGENT)只负责调工具与收束判断，不写正文
        # 工具使用原则与防串扰仅注入编排上下文，正文阶段改用干净人格提示词
        tools = [*self._registry.openai_tools(), _FINISH_TOOL]
        role = model_router.resolve(ROLE_AGENT)
        scratchpad = self._inject_guidance(messages)
        scratchpad.append(
            {
                "role": "system",
                "content": self._loop_instruction(),
            }
        )

        records: list[ToolCallRecord] = []
        meta: dict[str, Any] = {}
        step = 0

        with bind_session_context(user_id, group_id, persona_name):
            while step < steps_cap:
                step += 1
                if time.time() - start > budget:
                    logger.warning(
                        f"Agent循环超时({budget:.0f}s)，提前收敛",
                        command="AI",
                    )
                    break

                try:
                    message = await self._llm.chat_tools(
                        scratchpad,
                        tools,
                        model=role.model or None,
                        options=role.apply_to_options(
                            {"max_tokens": 4096}
                        ),
                        provider_name=role.provider or None,
                    )
                except Exception as e:
                    logger.error(
                        f"工具编排阶段LLM调用失败，转直接回复: {e}",
                        command="AI",
                        e=e,
                    )
                    break

                tool_calls = message.get("tool_calls") or []
                content = str(message.get("content") or "")
                if not tool_calls:
                    break

                scratchpad.append(
                    {
                        "role": "assistant",
                        "content": content,
                        "tool_calls": tool_calls,
                    }
                )

                finish_meta = self._parse_finish(tool_calls)
                if finish_meta is not None:
                    meta = finish_meta
                    break

                observations = await self._execute_calls(
                    tool_calls,
                    budget - (time.time() - start),
                    records,
                )
                scratchpad.extend(observations)

        # 正文一律由主模型(ROLE_CHAT)人格 pass 生成；仅群聊非直达且
        # 判定静默时跳过，省去无谓生成
        silent = (
            bool(meta.get("recommend_silence"))
            and bool(group_id)
            and not is_at_bot
        )
        if silent:
            response = PersonaResponse(
                reply_text="",
                recommend_silence=True,
                ask_clarify=bool(meta.get("ask_clarify")),
                bot_emotion=str(meta.get("bot_emotion") or "neutral"),
                tts_style_hint=str(meta.get("tts_style_hint", "")),
                sticker_mood_hint=str(meta.get("sticker_mood_hint", "")),
            )
        else:
            response = await self._compose_reply(messages, records, meta)

        return self._finalize(response, records, start, step)

    async def _compose_reply(
        self,
        messages: list[dict[str, Any]],
        records: list[ToolCallRecord],
        meta: dict[str, Any],
    ) -> PersonaResponse:
        """人格回复阶段：用主模型(ROLE_CHAT)受约束地写最终正文

        复刻旧响应器的"受约束生成"以保住拟人化：抽取人格系统提示词、
        把历史压缩为最近若干条、将用户这句话单独置于末尾作为待回复目标，
        并在用户轮末尾重申"回复模式"以就近锁定详略；正文以只含
        reply_text 的 JSON 产出（旧版验证：JSON 单字段比纯文本更能
        锁住长度、防铺写多段），情绪/静默等元信息仍由 finish 给出。
        这是拟人化的落点：无论工具编排阶段用多便宜的模型，正文始终
        由主模型按人格受约束生成。

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
            if r.metadata.get("output_kind") == _IMAGE_OUTPUT_KIND:
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

        直接抄用旧响应器的约束与字数硬约束，仅把输出格式由"只输出
        JSON"改为"只输出回复正文"——是否静默/澄清/情绪等元信息已由
        编排阶段的 finish 工具给出，正文无需再套 JSON。

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

    @staticmethod
    def _loop_instruction() -> str:
        """工具编排阶段指令（只讲循环机制，工具取舍原则交给 TOOL_GUIDANCE）

        返回:
            str: 指令文本
        """
        return (
            "你在工具编排阶段：按上面的工具使用原则决定要不要调用工具"
            "支撑回答，需要就调用、读结果后可继续；信息够了或判断该静默/"
            "该澄清时调用 finish 收束。本阶段只做工具决策与收束，不要写"
            "面向用户的正文。"
        )

    @staticmethod
    def _inject_guidance(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """把工具使用原则与多话题防串扰注入编排上下文

        追加到首个 system 内容末尾，仅供工具编排阶段使用；正文阶段
        改用干净人格提示词，不受工具指令污染。已注入时幂等返回。

        参数:
            messages: 原始消息列表

        返回:
            list[dict[str, Any]]: 注入后的消息副本
        """
        extra = f"{TOOL_GUIDANCE_PROMPT}\n\n{CROSSTALK_GUARD_PROMPT}\n\n"
        copied = [dict(m) for m in messages]
        for msg in copied:
            if msg.get("role") == "system" and msg.get("content"):
                if CROSSTALK_MARKER in msg["content"]:
                    return copied
                msg["content"] = f"{msg['content']}{extra}"
                return copied
        copied.insert(0, {"role": "system", "content": extra.strip()})
        return copied

    @staticmethod
    def _parse_finish(
        tool_calls: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """从工具调用中解析 finish 收束元信息

        参数:
            tool_calls: 模型返回的工具调用列表

        返回:
            dict | None: 命中 finish 时返回元信息字典，否则 None
        """
        for call in tool_calls:
            fn = call.get("function", {}) or {}
            if fn.get("name") != TOOL_FINISH:
                continue
            return _coerce_args(fn.get("arguments"))
        return None

    async def _execute_calls(
        self,
        tool_calls: list[dict[str, Any]],
        remaining: float,
        records: list[ToolCallRecord],
    ) -> list[dict[str, Any]]:
        """并发执行一批业务工具调用，产出回填的观察消息

        同时将每次调用的记录 append 到 records，供后续主模型
        正文 pass 作为证据使用（否则工具结果无法传递到回复阶段）。

        参数:
            tool_calls: 模型返回的工具调用列表
            remaining: 本批剩余时间预算（秒）
            records: 工具记录累加器（原地 append）

        返回:
            list[dict]: 与工具调用对应的 role=tool 观察消息
        """
        business = [
            call
            for call in tool_calls
            if (call.get("function", {}) or {}).get("name")
            != TOOL_FINISH
        ]
        results = await asyncio.gather(
            *(self._execute_one(call, remaining) for call in business),
            return_exceptions=False,
        )
        observations: list[dict[str, Any]] = []
        for call, (record, observation) in zip(
            business, results, strict=True
        ):
            records.append(record)
            observations.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "name": record.tool_name,
                    "content": observation,
                }
            )
        return observations

    async def _execute_one(
        self, call: dict[str, Any], remaining: float
    ) -> tuple[ToolCallRecord, str]:
        """执行单个工具调用并把结果/错误转为观察文本

        参数:
            call: 单个工具调用
            remaining: 剩余时间预算（秒）

        返回:
            tuple[ToolCallRecord, str]: (记录, 回填模型的观察文本)
        """
        fn = call.get("function", {}) or {}
        name = str(fn.get("name", ""))
        args = _coerce_args(fn.get("arguments"))
        record = ToolCallRecord(
            tool_name=name,
            args=dict(args),
            timestamp=time.time(),
        )
        tool = self._registry.get(name)
        if tool is None or tool.is_disabled:
            record.error = f"工具 '{name}' 不存在或已禁用"
            return record, record.error

        record.metadata = dict(tool.metadata)
        ok, err = _validate_args(tool, args)
        if not ok:
            record.error = err
            return record, f"参数错误: {err}"

        use_args = _filter_args(tool, args)
        timeout = min(DEFAULT_TOOL_TIMEOUT, max(remaining, 1.0))
        start = time.time()
        try:
            result = await asyncio.wait_for(
                tool.func(**use_args), timeout=timeout
            )
            record.result = (
                result if isinstance(result, str) else str(result)
            )
            record.success = True
        except TimeoutError:
            record.error = f"工具 '{name}' 超时（{timeout:.0f}s）"
            logger.warning(record.error, command="AI")
        except Exception as e:
            record.error = f"{type(e).__name__}: {e}"
            logger.warning(
                f"工具 '{name}' 执行失败: {e}", command="AI", e=e
            )
        record.elapsed = time.time() - start
        observation = record.result if record.success else record.error
        return record, observation or "（工具无输出）"

    def _finalize(
        self,
        response: PersonaResponse,
        records: list[ToolCallRecord],
        start: float,
        steps: int,
    ) -> AgentOutcome:
        """收敛循环产出，计算指标与图片URL

        参数:
            response: 角色化响应
            records: 工具调用记录
            start: 开始时间戳
            steps: 实际步数

        返回:
            AgentOutcome: 产出
        """
        elapsed = time.time() - start
        response.elapsed = elapsed
        return AgentOutcome(
            response=response,
            tool_calls=records,
            steps=steps,
            metrics={
                "total_calls": len(records),
                "success_calls": sum(r.success for r in records),
                "failed_calls": sum(not r.success for r in records),
                "tool_count": len(records),
            },
            image_url=_extract_image_url(records),
            elapsed=elapsed,
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


def _coerce_args(raw: Any) -> dict[str, Any]:
    """把工具调用 arguments 归一化为字典

    OpenAI 协议中 arguments 为 JSON 字符串，部分实现直接给字典，二者都兼容。

    参数:
        raw: 原始 arguments

    返回:
        dict[str, Any]: 参数字典，解析失败返回空字典
    """
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        loaded = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.debug(f"工具参数JSON解析失败: {raw!r}", command="AI")
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _validate_args(
    tool: Any, args: dict[str, Any]
) -> tuple[bool, str]:
    """基于 JSON Schema 校验必填参数

    参数:
        tool: 工具实例
        args: 参数字典

    返回:
        tuple[bool, str]: (是否通过, 错误信息)
    """
    schema = tool.parameters or {}
    required = schema.get("required", []) or []
    missing = [r for r in required if r not in args]
    if missing:
        return False, f"缺少必填参数: {', '.join(missing)}"
    return True, ""


def _filter_args(
    tool: Any, args: dict[str, Any]
) -> dict[str, Any]:
    """过滤掉 schema 未声明的多余参数

    参数:
        tool: 工具实例
        args: 原始参数

    返回:
        dict[str, Any]: 仅含合法键的参数
    """
    properties = (tool.parameters or {}).get("properties", {}) or {}
    if not properties:
        return dict(args)
    return {k: v for k, v in args.items() if k in properties}


def _extract_image_url(
    records: list[ToolCallRecord],
) -> str | None:
    """从工具记录中提取生成的图片URL

    参数:
        records: 工具调用记录

    返回:
        str | None: 图片URL或None
    """
    for record in records:
        if not record.success:
            continue
        if record.metadata.get("output_kind") != _IMAGE_OUTPUT_KIND:
            continue
        url = record.result.strip()
        if url.startswith("http"):
            return url
    return None
