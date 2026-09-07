"""回复生成器

从 ReplyProcessor 中抽出的回复生成逻辑，负责处理
视觉路由、图片描述注入、Agent循环、安全过滤、
LLM调用与失败兜底等完整回复生成流程。
"""

import random
from typing import Any

from liuying.utils.log import logger

from ..agent.runner import AgentResult, AgentRunner
from ..config import get_config
from ..core.llm import llm_helper
from ..core.llm.model_router import ROLE_CHAT, model_router
from ..core.persona import persona_manager
from ..core.safety import SafetyFilter, SafetyRefusalError
from ..core.vision import summarize_image, vision_router
from .helpers import ReplyPipeline
from .types import ReplyContext

_FALLBACK_REPLIES: list[str] = [
    "嗯...让我想想",
    "稍等一下~",
    "我有点没理解，能再说一遍吗",
    "抱歉刚才走神了",
]
"""兜底回复池"""


class ReplyGenerator:
    """回复生成器

    Agent启用时走Agent循环，否则直接LLM对话。
    启用安全过滤时包裹LLM调用，命中拒绝模板则重试一次。
    当上下文含图片时：先尝试通过视觉路由切换多模态消息；
    路由失败则降级到图片描述注入文本。
    """

    async def _describe_image_for_text(
        self, ctx: ReplyContext
    ) -> str:
        """为纯文本对话生成图片描述注入

        当 provider 不支持视觉或视觉路由失败时，使用
        summarize_image 获取描述，并拼接到用户消息文本中。

        参数:
            ctx: 回复上下文（含图片数据）

        返回:
            str: 图片描述文本，失败返回空串
        """
        if not ctx.image_data:
            return ""
        try:
            summary = await summarize_image(
                ctx.image_data,
                mime=ctx.image_mime,
                llm_helper=llm_helper,
            )
            if summary.success and summary.description:
                return summary.description.strip()
            return ""
        except Exception as e:
            logger.debug(
                f"图片描述生成失败: {e}", command="AI", e=e
            )
            return ""

    async def _resolve_vision_route(
        self, ctx: ReplyContext
    ) -> tuple[str | None, str | None, bool]:
        """解析视觉能力路由

        当上下文含图片时，调用 vision_router 路由到支持视觉的
        provider；返回 (provider, model, use_multimodal)。

        参数:
            ctx: 回复上下文

        返回:
            tuple: (provider名, 模型名, 是否使用多模态消息)
        """
        if not ctx.image_data:
            return None, None, False
        try:
            route = await vision_router.route_vision_request()
            if route.success:
                return route.provider or None, (
                    route.model or None
                ), True
            return None, None, False
        except Exception as e:
            logger.debug(
                f"视觉路由解析失败，降级到文本描述: {e}",
                command="AI",
                e=e,
            )
            return None, None, False

    async def generate_reply(
        self,
        messages: list[dict[str, str]],
        ctx: ReplyContext,
    ) -> tuple[str, AgentResult | None]:
        """生成回复

        Agent启用时走Agent循环，否则直接LLM对话。
        启用安全过滤时包裹LLM调用，命中拒绝模板则重试一次。
        当上下文含图片时：先尝试通过视觉路由切换多模态消息；
        路由失败则降级到图片描述注入文本。

        参数:
            messages: 完整消息列表
            ctx: 回复上下文

        返回:
            tuple[str, AgentResult | None]: (回复文本, Agent结果)
        """
        use_messages: list[dict[str, Any]] = list(messages)
        vision_provider: str | None = None
        vision_model: str | None = None

        if ctx.image_data:
            vp, vm, use_mm = await self._resolve_vision_route(
                ctx
            )
            if use_mm:
                vision_provider = vp
                vision_model = vm
                use_messages = ReplyPipeline.build_vision_messages(
                    messages[0].get("content", "") if messages else "",
                    [
                        m for m in messages
                        if m.get("role") != "system"
                    ],
                    ctx,
                )
            else:
                desc = await self._describe_image_for_text(ctx)
                if desc:
                    ctx_text = ctx.text or ""
                    # 临时注入图片描述构建消息，构建后恢复原始文本
                    # 避免污染后续主动学习与持久化的用户原始消息
                    original_text = ctx.text
                    ctx.text = (
                        f"{ctx_text}\n[用户附带图片描述: {desc}]"
                        if ctx_text
                        else f"[用户发了一张图片: {desc}]"
                    )
                    try:
                        use_messages = ReplyPipeline.build_messages(
                            messages[0].get("content", "") if messages else "",
                            [
                                m for m in messages
                                if m.get("role") != "system"
                            ],
                            ctx,
                        )
                    finally:
                        ctx.text = original_text

        if get_config("AGENT", {}).get("enabled", True):
            try:
                result = await AgentRunner.run_agent(
                    use_messages,
                    llm_helper,
                    user_id=ctx.user_id,
                    group_id=ctx.group_id,
                    use_llm_planning=True,
                    persona_name=ctx.persona_name,
                    has_image=vision_provider is not None,
                )
                if (
                    result.response
                    and result.response.recommend_silence
                ):
                    return "", result
                return result.text, result
            except Exception as e:
                logger.warning(
                    f"Agent执行失败，降级到普通对话: {e}",
                    command="AI",
                    e=e,
                )

        # 接入模型按角色路由：视觉路由优先，否则使用 ROLE_CHAT 配置
        chat_role = model_router.resolve(ROLE_CHAT)
        use_model = vision_model or chat_role.model or None
        use_provider = vision_provider or chat_role.provider or None
        chat_options = chat_role.apply_to_options()

        if not get_config("SAFETY_FILTER_ENABLED", True):
            try:
                reply_text = await llm_helper.chat_text(
                    use_messages,
                    model=use_model,
                    options=chat_options,
                    provider_name=use_provider,
                )
                return reply_text, None
            except Exception as e:
                logger.error(
                    f"LLM对话调用失败: {e}", command="AI", e=e
                )
                return random.choice(_FALLBACK_REPLIES), None

        retry_messages = list(use_messages)
        retry_persona = await persona_manager.get_persona_by_name(
            ctx.persona_name
        )
        retry_name = retry_persona.get("name") or "AI"
        retry_hint = (
            f"\n[重要提示] 请直接以{retry_name}的身份回复，"
            "不要使用模板化拒绝用语，不要提及自己是AI或助手。"
            "如果确实无法回答，简短说一句即可。"
        )
        retry_messages.append(
            {
                "role": "system",
                "content": retry_hint,
            }
        )

        try:

            async def _first_call() -> str:
                """首次LLM调用

                返回:
                    str: LLM回复文本
                """
                return await llm_helper.chat_text(
                    use_messages,
                    model=use_model,
                    options=chat_options,
                    provider_name=use_provider,
                )

            async def _retry_call() -> str:
                """重试LLM调用

                返回:
                    str: LLM回复文本
                """
                return await llm_helper.chat_text(
                    retry_messages,
                    model=use_model,
                    options=chat_options,
                    provider_name=use_provider,
                )

            reply_text = await SafetyFilter.sanitize_or_retry(
                call=_first_call,
                retry_call=_retry_call,
                extract=lambda r: r or "",
                purpose="chat",
            )
            return reply_text, None
        except SafetyRefusalError as e:
            logger.warning(
                f"安全过滤拦截，丢弃本轮回复: source={e.source} "
                f"reason={e.reason}",
                command="AI",
                e=e,
            )
            return "", None
        except Exception as e:
            logger.error(
                f"LLM对话调用失败: {e}", command="AI", e=e
            )
            return random.choice(_FALLBACK_REPLIES), None
