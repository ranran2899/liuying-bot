"""Agent核心循环（三层架构）

规划-执行-响应三层分离：
1. TurnPlanner 决策回合行为（动作/输出模式/工具意图）
2. ToolExecutor 按规划调用工具，合成为证据
3. PersonaResponder 整合证据与人格，生成最终回复

对外保留 run_agent 接口，内部改用新架构。
"""

from dataclasses import dataclass, field
import time
from typing import Any

from liuying.utils.log import logger

from ..config import get_config
from ..core.llm import LLMHelper
from .query_rewriter import contextual_query_rewriter
from .runtime.executor import ToolExecutor
from .runtime.plan_types import TurnPlan
from .runtime.planner import TurnPlanner
from .runtime.responder import PersonaResponder, PersonaResponse
from .runtime.session_context import bind_session_context
from .runtime.tool_catalog import semantic_tool_guidance
from .tools import ToolRegistry, tool_registry

# 多话题防串扰硬约束（参考参考插件 runner.py 的防串话 system 消息）
_ANTI_CROSSTALK_PROMPT = (
    "群聊里通常多个话题并行：A 群友讨论地震、B 群友讨论自己的近况、"
    "C 群友在闲扯，时间相近不代表语义相关。\n"
    "硬性规则：\n"
    "1. 你回复的是上下文中标记为当前消息的那一条；其它发言只是背景，"
    "不要把它们的内容拿来回答当前问题。\n"
    "2. 不要把不同人说的关键词（地名、人名、状态）跨话题拼接。"
    "拿不准时宁可简短、含糊或承认不知道，也不要把无关上下文糊上去。"
)
"""多话题防串扰硬约束提示"""


@dataclass(slots=True)
class AgentResult:
    """Agent执行结果

    Attributes:
        text: 最终回复文本
        tool_calls: 工具调用记录列表
        steps: 实际执行的步数
        elapsed: 总耗时（秒）
        plan: 回合规划
        response: 角色化响应
        metrics: 执行指标
        image_url: 生成的图片URL，None表示无图片
    """

    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    steps: int = 0
    elapsed: float = 0.0
    plan: TurnPlan | None = None
    response: PersonaResponse | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    image_url: str | None = None

    @property
    def metadata(self) -> dict[str, Any]:
        """元信息字典"""
        return {
            "plan": self.plan.to_dict() if self.plan else {},
            "response": (
                self.response.to_dict() if self.response else {}
            ),
            "metrics": self.metrics,
            "steps": self.steps,
            "elapsed": round(self.elapsed, 3),
            "silence": (
                self.response.is_silence if self.response else False
            ),
            "sticker_mood_hint": (
                self.response.sticker_mood_hint if self.response else ""
            ),
            "tts_style_hint": (
                self.response.tts_style_hint if self.response else ""
            ),
            "image_url": self.image_url or "",
        }


class AgentRunner:
    """Agent核心循环执行器

    封装三层架构（规划-执行-响应）的入口与辅助方法，
    所有方法均为静态方法，可通过类名直接调用。
    """

    @staticmethod
    async def run_agent(
        messages: list[dict[str, str]],
        llm_helper: LLMHelper,
        registry: ToolRegistry | None = None,
        max_steps: int | None = None,
        time_budget: float | None = None,
        user_id: str = "",
        group_id: str | None = None,
        has_image: bool = False,
        use_llm_planning: bool = True,
        persona_name: str = "default",
    ) -> AgentResult:
        """执行Agent循环（三层架构）

        参数:
            messages: 对话消息列表（最后一条为用户消息）
            llm_helper: LLM助手实例
            registry: 工具注册表，None时用单例
            max_steps: 最大步数（保留兼容，实际由规划决定）
            time_budget: 时间预算（秒），None时用配置默认
            user_id: 用户ID（用于人格与记忆）
            group_id: 群组ID
            has_image: 是否包含图片
            use_llm_planning: 是否启用LLM精细规划，False时用规则快速决策
            persona_name: 当前bot人格名（用于记忆/情绪隔离）

        返回:
            AgentResult: 执行结果
        """
        start_time = time.time()
        use_registry = registry or tool_registry
        use_budget = time_budget if time_budget is not None else float(
            get_config("AGENT", {}).get("response_timeout", 180)
        )

        if not messages:
            return AgentResult(text="", elapsed=0.0)

        user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
                break

        context_summary = AgentRunner._build_context_summary(messages)

        # ===== 第1层：规划 =====
        # 规则快速路径：极短消息（≤10字符）且无图片时跳过LLM规划，
        # 直接用规则决策，省去规划层LLM调用的token消耗
        use_llm_for_plan = use_llm_planning
        if use_llm_for_plan and not has_image:
            stripped = user_message.strip()
            if len(stripped) <= 10 and "?" not in stripped and "？" not in stripped:
                use_llm_for_plan = False

        planner = TurnPlanner(llm=llm_helper)
        try:
            plan = await planner.plan(
                user_message=user_message,
                context_summary=context_summary,
                has_image=has_image,
                use_llm=use_llm_for_plan,
            )
        except Exception as e:
            logger.warning(
                f"规划失败，降级到快速规则: {e}",
                command="AI",
                e=e,
            )
            plan = planner.plan_fast(user_message, context_summary, has_image)

        if not plan.user_message:
            plan.user_message = user_message

        # 应用 max_steps 上限（兼容旧参数）
        if max_steps and max_steps < plan.max_steps:
            plan.max_steps = max_steps

        logger.debug(
            f"回合规划: action={plan.action} mode={plan.output_mode} "
            f"need_tool={plan.need_tool} reason={plan.reason}",
            command="AI",
        )

        # 注入多话题防串扰硬约束 + 语义工具指导到 system 消息，
        # 供响应器消费（参考参考插件 runner.py 的 system 消息注入）
        AgentRunner._inject_guidance_to_messages(messages)

        # 需要工具时调用查询改写器，生成高质量检索计划，
        # 避免 LLM 规划器直接拿用户口语当 query（参考参考插件核心创新）
        if plan.need_tool:
            await AgentRunner._apply_query_rewrite(
                plan, user_message, context_summary, llm_helper, has_image
            )

        # 静默场景直接返回
        if plan.is_silence:
            elapsed = time.time() - start_time
            return AgentResult(
                text="",
                elapsed=elapsed,
                plan=plan,
                response=PersonaResponse(
                    reply_text="",
                    recommend_silence=True,
                    elapsed=elapsed,
                ),
                metrics={"silence": True},
            )

        # ===== 第2层：执行 =====
        with bind_session_context(user_id, group_id, persona_name):
            executor = ToolExecutor(registry=use_registry)
            if plan.need_tool:
                try:
                    records = await executor.execute_chain(
                        plan, time_budget=use_budget
                    )
                except Exception as e:
                    logger.warning(
                        f"工具链执行失败: {e}",
                        command="AI",
                        e=e,
                    )
                    records = []
            else:
                records = []

            # 检查时间预算
            elapsed = time.time() - start_time
            if elapsed > use_budget:
                logger.warning(
                    f"Agent循环超时({elapsed:.1f}s)，跳过响应生成",
                    command="AI",
                )
                return AgentRunner._build_timeout_result(
                    records, plan, executor, start_time
                )

            # ===== 第3层：响应 =====
            responder = PersonaResponder(
                llm=llm_helper,
            )
            try:
                response = await responder.respond(
                    plan=plan,
                    evidence=executor.evidence,
                    user_message=user_message,
                    messages=messages,
                    user_id=user_id,
                    group_id=group_id,
                )
            except Exception as e:
                logger.error(
                    f"响应生成失败: {e}",
                    command="AI",
                    e=e,
                )
                response = PersonaResponse(
                    reply_text="出了点小问题，待会再试试~",
                    elapsed=time.time() - start_time,
                )

            elapsed = time.time() - start_time
            tool_calls = [r.to_dict() for r in records]
            image_url = AgentRunner._extract_image_url(records)

            return AgentResult(
                text=response.reply_text,
                tool_calls=tool_calls,
                steps=len(records),
                elapsed=elapsed,
                plan=plan,
                response=response,
                metrics={
                    "execution": executor.metrics.to_dict(),
                    "tool_count": len(records),
                },
                image_url=image_url,
            )

    @staticmethod
    def _inject_guidance_to_messages(
        messages: list[dict[str, str]],
    ) -> None:
        """注入多话题防串扰和语义工具指导到 system 消息

        将防串扰硬约束和语义工具指导追加到 messages 的首个 system
        消息内容末尾，供响应器消费。无 system 消息时新建一条。

        参数:
            messages: 消息列表（原地修改）
        """
        guidance = semantic_tool_guidance()
        extra = f"\n\n{guidance}\n\n{_ANTI_CROSSTALK_PROMPT}"
        for msg in messages:
            if msg.get("role") == "system" and msg.get("content"):
                msg["content"] = f"{msg['content']}{extra}"
                return
        messages.insert(0, {"role": "system", "content": extra.strip()})

    @staticmethod
    async def _apply_query_rewrite(
        plan: TurnPlan,
        user_message: str,
        context_summary: str,
        llm: LLMHelper,
        has_image: bool,
    ) -> None:
        """调用查询改写器，将改写结果注入 plan

        需要工具调用时，先用查询改写器生成高质量检索计划，
        将 primary_query 注入 plan.tool_args 的 query 字段（如果存在），
        将 query_candidates 存入 plan.query_candidates 供执行器变体重试。

        参数:
            plan: 回合规划（原地修改）
            user_message: 用户消息
            context_summary: 上下文摘要
            llm: LLM助手
            has_image: 是否有图片
        """
        try:
            rewrite = await contextual_query_rewriter(
                llm=llm,
                history_new=context_summary,
                history_last=user_message,
                images=["image"] if has_image else None,
                quoted_message="",
                topic_hint="",
            )
        except Exception as e:
            logger.debug(
                f"查询改写失败，用原始消息: {e}", command="AI"
            )
            return

        if rewrite.primary_query and "query" in plan.tool_args:
            plan.tool_args["query"] = rewrite.primary_query
        if rewrite.query_candidates:
            plan.query_candidates = list(rewrite.query_candidates)
        logger.debug(
            f"查询改写: primary={rewrite.primary_query[:60]} "
            f"candidates={len(rewrite.query_candidates)}",
            command="AI",
        )

    @staticmethod
    def _build_context_summary(messages: list[dict[str, str]]) -> str:
        """构建上下文摘要

        从对话历史中提取最近几条消息作为上下文摘要。

        参数:
            messages: 对话消息列表

        返回:
            str: 上下文摘要文本
        """
        if not messages:
            return ""
        recent = messages[-6:]
        parts: list[str] = []
        for msg in recent:
            role = msg.get("role", "user")
            content = msg.get("content", "")[:100]
            if not content:
                continue
            role_label = {"user": "用户", "assistant": "AI", "system": "系统"}
            parts.append(f"{role_label.get(role, role)}: {content}")
        return "\n".join(parts)

    @staticmethod
    def _build_timeout_result(
        records: list,
        plan: TurnPlan,
        executor: ToolExecutor,
        start_time: float,
    ) -> AgentResult:
        """构建超时降级结果

        参数:
            records: 已完成的工具调用记录
            plan: 回合规划
            executor: 工具执行器
            start_time: 开始时间

        返回:
            AgentResult: 降级结果
        """
        tool_calls = [r.to_dict() for r in records]
        fallback_text = "我查到了一些信息，但响应生成超时了，请稍后再试~"
        if records:
            last_success = next(
                (r for r in reversed(records) if r.success), None
            )
            if last_success and last_success.result:
                fallback_text = last_success.result[:200]

        elapsed = time.time() - start_time
        return AgentResult(
            text=fallback_text,
            tool_calls=tool_calls,
            steps=len(records),
            elapsed=elapsed,
            plan=plan,
            response=PersonaResponse(
                reply_text=fallback_text,
                elapsed=elapsed,
            ),
            metrics={
                "execution": executor.metrics.to_dict(),
                "timeout": True,
                "tool_count": len(records),
            },
            image_url=AgentRunner._extract_image_url(records),
        )

    @staticmethod
    def _extract_image_url(records: list) -> str | None:
        """从工具调用记录中提取生成的图片URL

        仅识别 output_kind 为 image_url 且调用成功的首个结果。

        参数:
            records: 工具调用记录列表

        返回:
            str | None: 图片URL或None
        """
        for record in records:
            if not record.success:
                continue
            if record.metadata.get("output_kind") != "image_url":
                continue
            url = record.result.strip()
            if url and not url.startswith("图片生成失败"):
                return url
        return None
