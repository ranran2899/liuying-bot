"""Agent 核心循环入口

对外保留 run_agent / AgentResult 接口，内部改为驱动统一 ReAct 循环
（agent.runtime.loop.AgentLoop）。静默/澄清/直达必答等回合级裁决集中
在本模块单点完成，消除旧架构中规划器与响应器双份维护。
"""

from dataclasses import dataclass, field
from typing import Any

from liuying.utils.log import logger

from .runtime.loop import AgentLoop, PersonaResponse


@dataclass(slots=True)
class AgentResult:
    """Agent执行结果

    Attributes:
        text: 最终回复文本
        tool_calls: 工具调用记录列表
        steps: 实际执行的步数
        elapsed: 总耗时（秒）
        response: 角色化响应
        metrics: 执行指标
        image_url: 生成的图片URL，None表示无图片
    """

    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    steps: int = 0
    elapsed: float = 0.0
    response: PersonaResponse | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    image_url: str | None = None

    @property
    def metadata(self) -> dict[str, Any]:
        """元信息字典"""
        return {
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


_CLARIFY_TEMPLATES = (
    "嗯……能再说得详细一点吗？",
    "我没有完全理解，可以再解释一下吗？",
    "你是想问……吗？还是别的呢？",
)


class AgentRunner:
    """Agent核心循环执行器

    封装统一 ReAct 循环的入口与回合级裁决辅助方法，
    所有方法均为静态方法，可通过类名直接调用。
    """

    @staticmethod
    async def run_agent(
        messages: list[dict[str, Any]],
        llm_helper: Any,
        registry: Any = None,
        max_steps: int | None = None,
        time_budget: float | None = None,
        user_id: str = "",
        group_id: str | None = None,
        has_image: bool = False,
        use_llm_planning: bool = True,
        persona_name: str = "default",
        is_at_bot: bool = False,
    ) -> AgentResult:
        """执行统一 ReAct 循环

        参数:
            messages: 对话消息列表（最后一条为用户消息）
            llm_helper: LLM助手实例
            registry: 工具注册表，None时用单例
            max_steps: 最大步数，None时用配置默认
            time_budget: 时间预算（秒），None时用配置默认
            user_id: 用户ID（用于人格与记忆）
            group_id: 群组ID
            has_image: 是否包含图片
            use_llm_planning: 兼容旧参数，False时走无工具快速直答
            persona_name: 当前bot人格名（用于记忆/情绪隔离）
            is_at_bot: 是否@bot或直呼bot（用于直达必答裁决）

        返回:
            AgentResult: 执行结果
        """
        if not messages:
            return AgentResult(text="", elapsed=0.0)

        loop = AgentLoop(llm=llm_helper, registry=registry)
        outcome = await loop.run(
            messages,
            user_id=user_id,
            group_id=group_id,
            persona_name=persona_name,
            is_at_bot=is_at_bot,
            max_steps=max_steps,
            time_budget=time_budget,
        )

        return AgentRunner._to_result(
            outcome, group_id=group_id, is_at_bot=is_at_bot
        )

    @staticmethod
    def _to_result(
        outcome: Any, group_id: str | None, is_at_bot: bool
    ) -> AgentResult:
        """把循环产出转成 AgentResult，并做回合级静默/澄清裁决

        参数:
            outcome: AgentOutcome
            group_id: 群组ID，None为私聊
            is_at_bot: 消息是否直达bot

        返回:
            AgentResult: 最终结果
        """
        response = outcome.response
        direct = group_id is None or is_at_bot

        # 直达消息（私聊/@bot/回复bot）禁止静默：等同无视用户
        if direct and response.recommend_silence:
            response.recommend_silence = False
            logger.debug("直达消息已取消静默建议", command="AI")

        # 澄清但正文为空时补一句模板澄清
        if response.ask_clarify and not response.reply_text.strip():
            response.reply_text = _CLARIFY_TEMPLATES[0]
            response.recommend_silence = False

        tool_calls = [r.to_dict() for r in outcome.tool_calls]
        return AgentResult(
            text=response.reply_text,
            tool_calls=tool_calls,
            steps=outcome.steps,
            elapsed=outcome.elapsed,
            response=response,
            metrics=outcome.metrics,
            image_url=outcome.image_url,
        )


__all__ = ["AgentResult", "AgentRunner"]
