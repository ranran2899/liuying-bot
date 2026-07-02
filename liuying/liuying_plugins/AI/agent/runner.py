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
from .runtime.execution.executor import ToolExecutor
from .runtime.planning.planner import TurnPlanner
from .runtime.planning.types import TurnPlan
from .runtime.response.responder import PersonaResponder, PersonaResponse
from .tools import ToolRegistry, tool_registry


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
        llm_helper,
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
            get_config("RESPONSE_TIMEOUT", 180)
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
        planner = TurnPlanner(llm=llm_helper)
        try:
            plan = await planner.plan(
                user_message=user_message,
                context_summary=context_summary,
                has_image=has_image,
                use_llm=use_llm_planning,
            )
        except Exception as e:
            logger.warning(
                f"规划失败，降级到快速规则: {e}",
                command="AI",
                e=e,
            )
            plan = planner.plan_fast(user_message, context_summary, has_image)

        # 将会话上下文回填到规划中，供执行器自动注入工具参数
        plan.user_id = user_id
        plan.group_id = group_id
        plan.persona_name = persona_name
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


# 向后兼容别名：保持模块级函数可被直接导入
run_agent = AgentRunner.run_agent
_build_context_summary = AgentRunner._build_context_summary
_build_timeout_result = AgentRunner._build_timeout_result
_extract_image_url = AgentRunner._extract_image_url
