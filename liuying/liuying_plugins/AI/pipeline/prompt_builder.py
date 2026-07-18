"""系统提示词构建器

从 ReplyProcessor 中抽出的提示词组装逻辑，负责整合人格、
上下文、情绪、记忆、群风格、话题线程、社交上下文、
安全过滤、回复风格策略、环境感知等所有提示词片段，
并通过提示词钩子注册表支持热插拔注入。
"""

from datetime import datetime

from liuying.utils.log import logger

from ..config import get_config
from ..core.context import ContextPolicy, context_manager, thread_tracker
from ..core.emotion import emotion_manager
from ..core.group import (
    ProfileToolkit,
    group_profile,
    group_social,
)
from ..core.llm import llm_helper
from ..core.memory import memory_manager
from ..core.peer_awareness import peer_awareness
from ..core.persona import persona_manager
from ..core.prompt_hooks import HookContext, hook_registry
from ..core.safety import SafetyFilter
from .humanize import HumanizeToolkit
from .style_policy import ReplyStylePolicy
from .types import ReplyContext


class PromptBuilder:
    """系统提示词构建器

    使用用户当前激活的人格构建提示词，并注入对应人格的
    情绪状态与记忆，确保人设间数据隔离。
    同时执行提示词钩子注册表中的钩子，支持热插拔注入。
    """

    async def build_system_prompt(
        self, ctx: ReplyContext, history: list[dict[str, str]]
    ) -> str:
        """构建系统提示词

        参数:
            ctx: 回复上下文
            history: 历史消息列表（用于anti-loop检测）

        返回:
            str: 完整系统提示词
        """
        persona = await persona_manager.get_user_persona_config(
            ctx.user_id
        )
        base_prompt = await persona_manager.build_system_prompt(
            persona, ctx.user_id, ctx.group_id
        )

        context_prompt = await context_manager.build_full_context_prompt(
            ctx.group_id
        )

        emotion_prompt = await emotion_manager.build_emotion_prompt_for_user(
            ctx.user_id, ctx.group_id, persona_name=ctx.persona_name
        )

        memory_prompt = ""
        if get_config("MEMORY_ENABLED", True):
            try:
                memory_prompt = await memory_manager.build_memory_prompt(
                    ctx.user_id,
                    ctx.text,
                    ctx.group_id,
                    top_k=get_config("MEMORY_RECALL_TOP_K", 5),
                    persona_name=ctx.persona_name,
                )
            except Exception as e:
                logger.debug(
                    f"记忆召回失败，降级到无记忆模式: {e}",
                    command="AI",
                    e=e,
                )

        # 构建提示词钩子上下文
        hook_ctx = HookContext(
            user_id=ctx.user_id,
            group_id=ctx.group_id or "",
            is_private=ctx.is_private,
            message_text=ctx.text,
            has_image_input=ctx.image_data is not None,
            current_time_str=datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            persona_name=ctx.persona_name,
        )
        registry = hook_registry

        # system_prelude 钩子：在基础提示词之前注入
        prelude_chunks = await registry.run_all(
            hook_ctx, phase="system_prelude"
        )

        parts = [base_prompt, context_prompt, emotion_prompt, memory_prompt]

        # system_context 钩子：在记忆之后注入上下文补充
        context_chunks = await registry.run_all(
            hook_ctx, phase="system_context"
        )
        parts.extend(context_chunks)

        parts.append(context_manager.get_time_flavor_prompt())

        if ctx.group_id:
            try:
                style = await group_profile.get_or_extract_style(
                    ctx.group_id, ctx.text, llm_helper
                )
                style_prompt = ProfileToolkit.build_group_style_prompt_block(style)
                if style_prompt:
                    parts.append(style_prompt)
            except Exception as e:
                logger.debug(
                    f"注入群风格失败: {e}", command="AI", e=e
                )

            # 话题线程追踪：记录用户消息并注入当前话题上下文
            if get_config("THREAD_TRACKER_ENABLED", True):
                thread_tracker.track_message(
                    group_id=ctx.group_id,
                    user_id=ctx.user_id,
                    text=ctx.text,
                )
                thread_ctx = thread_tracker.get_thread_context(
                    ctx.group_id
                )
                if thread_ctx:
                    parts.append(
                        f"\n{thread_ctx}\n"
                    )

            # 注入群社交上下文（角色/关系/复读跟随提示）
            if get_config("SOCIAL_INTELLIGENCE_ENABLED", True):
                social_prompt = (
                    group_social.build_social_prompt_block(
                        ctx.group_id, ctx.user_id
                    )
                )
                if social_prompt:
                    parts.append(social_prompt)

        if get_config("SAFETY_FILTER_ENABLED", True):
            parts.append(SafetyFilter.build_prompt_injection_guard())

        # 注入回复风格策略：防止堆砌网络热词/模板化口癖
        has_visual = ctx.image_data is not None
        parts.append(
            ReplyStylePolicy.build_style_policy_prompt(
                has_visual_context=has_visual,
            )
        )
        if has_visual:
            parts.append(
                ReplyStylePolicy.build_visual_identity_guard()
            )

        # 注入环境感知提示词（提醒AI不要将其他插件/其他bot功能说成自己能力）
        if get_config("PEER_AWARENESS_ENABLED", True):
            parts.append(peer_awareness.build_peer_awareness_prompt())

        if (
            ctx.group_id
            and get_config("FRAGMENT_STYLE", "prompt") == "prompt"
        ):
            parts.append(HumanizeToolkit.build_group_chat_style_prompt())

        anti_loop = ContextPolicy.build_anti_loop_hint(history)
        if anti_loop:
            parts.append(anti_loop)

        # system_postlude 钩子：在所有提示词组装完成后注入
        postlude_chunks = await registry.run_all(
            hook_ctx, phase="system_postlude"
        )
        parts.extend(postlude_chunks)

        # prelude 作为最前置内容
        if prelude_chunks:
            parts = prelude_chunks + parts

        return "".join(parts)
