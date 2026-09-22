"""统一 ReAct Agent 循环（工具编排阶段）

以 ReAct 闭环驱动"推理 -> 原生 function-calling 调用工具 -> 观察结果
-> 再决策"，但把"工具编排"与"写正文"解耦：

- 本模块只负责工具编排：循环模型(ROLE_AGENT，可为便宜模型)判断/调用工具
  与收束判断（是否静默/澄清、情绪/TTS/贴纸提示），通过 ``finish`` 元工具结束；
- 正文一律由 ROLE_CHAT（主模型）的一次干净人格 pass 生成，该职责已拆到
  ``reply_composer.ReplyComposer``，本模块仅在收束后委托其产出正文，
  以保证拟人化语气——这是拟人化的核心。

工具执行保留参数校验、超时、会话上下文绑定，异常以观察文本回灌供模
型自我纠错；HTTP 全失败时 chat_tools 降级为直答，人格 pass 仍会兼底生成。
"""

import asyncio
import json
import time
from typing import Any

from liuying.utils.log import logger

from ...config import get_config
from ...core.llm import LLMHelper, llm_helper
from ...core.llm.model_router import ROLE_AGENT, model_router
from ...pipeline.style_policy import (
    CROSSTALK_GUARD_PROMPT,
    CROSSTALK_MARKER,
    TOOL_GUIDANCE_PROMPT,
)
from ...tools import ToolRegistry, tool_registry
from .constants import DEFAULT_TOOL_TIMEOUT, IMAGE_OUTPUT_KIND
from .reply_composer import ReplyComposer
from .session_context import bind_session_context
from .types import AgentOutcome, PersonaResponse, ToolCallRecord

TOOL_FINISH = "finish"
"""收束元工具名：工具编排阶段调用它结束本回合（不写正文）"""

_DEFAULT_MAX_STEPS = 10
"""默认最大循环步数（与 config_items AGENT.max_steps 默认口径一致）"""

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


class AgentLoop:
    """统一 ReAct 循环执行器（工具编排阶段）"""

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
        self._composer = ReplyComposer(llm=self._llm)

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
            response = await self._composer.compose(messages, records, meta)

        return self._finalize(response, records, start, step)

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
        if record.metadata.get("output_kind") != IMAGE_OUTPUT_KIND:
            continue
        url = record.result.strip()
        if url.startswith("http"):
            return url
    return None
