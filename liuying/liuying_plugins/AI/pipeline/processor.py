"""回复处理主流程

整合权限检查、群禁言感知、人格管理、记忆召回、上下文压缩、
Agent循环、安全过滤、拟人化处理、贴纸决策、碎片化分段、
持久化等环节，构建完整的对话回复流水线。
"""

import asyncio
import random
import time
from typing import Any

from nonebot_plugin_alconna import Image

from liuying.models.ban_console import BanConsole
from liuying.utils.log import logger

from ..agent.runner import AgentResult, run_agent
from ..config import get_config
from ..core.context import (
    build_anti_loop_hint,
    compress_context_if_needed,
    context_manager,
    has_silence_control_marker,
)
from ..core.emotion import emotion_manager
from ..core.group import (
    build_group_style_prompt_block,
    group_profile,
    group_social,
    is_group_muted,
    refresh_bot_group_mute_state,
)
from ..core.llm import (
    llm_helper,
    start_conversation_tracking,
    stop_conversation_tracking,
)
from ..core.memory import memory_manager
from ..core.persona import persona_manager
from ..core.safety import (
    SafetyRefusalError,
    build_prompt_injection_guard,
    sanitize_or_retry,
    token_quota_service,
)
from ..core.vision import summarize_image, vision_router
from ..models.conversation_record import ConversationRecord
from .helpers import (
    build_messages,
    build_segments,
    build_vision_messages,
    humanize_reply,
    persist_conversation,
)
from .humanize import build_group_chat_style_prompt
from .sticker import sticker_manager
from .types import ReplyContext, ReplyResult

_FALLBACK_REPLIES: list[str] = [
    "嗯...让我想想",
    "稍等一下~",
    "我有点没理解，能再说一遍吗",
    "抱歉刚才走神了",
]
"""兜底回复池"""

_TTS_AUTO_TEXT_MIN_LEN = 5
"""自动TTS最小文本长度"""

_QUOTA_INSUFFICIENT_TPL: str = (
    "咦？你的token似乎不足捏（剩余 {remaining} token），"
    "去兑换铜币再试试看~"
)
"""额度不足提示模板"""


class ReplyProcessor:
    """回复处理器

    整合所有core服务和pipeline组件，编排完整的对话回复流程。
    """

    async def _check_permission(
        self, ctx: ReplyContext
    ) -> bool:
        """权限检查（含BanConsole与群禁言感知）

        参数:
            ctx: 回复上下文

        返回:
            bool: 是否允许回复
        """
        try:
            if await BanConsole.is_ban(ctx.user_id, ctx.group_id):
                logger.debug(
                    f"用户被ban，跳过回复: {ctx.user_id}",
                    command="AI",
                )
                return False
        except Exception as e:
            logger.debug(
                f"权限检查异常（继续回复）: {e}",
                command="AI",
                e=e,
            )

        if ctx.group_id and get_config("GROUP_MUTE_AWARE", True):
            if is_group_muted(ctx.group_id):
                logger.info(
                    f"群 {ctx.group_id} bot处于禁言期，本轮跳过回复",
                    command="AI",
                    group_id=ctx.group_id,
                )
                return False

        return True

    async def _refresh_mute_state(
        self, ctx: ReplyContext, bot: Any
    ) -> None:
        """主动刷新群禁言状态

        参数:
            ctx: 回复上下文
            bot: Bot对象
        """
        if not ctx.group_id or not bot:
            return
        if not get_config("GROUP_MUTE_AWARE", True):
            return
        try:
            await refresh_bot_group_mute_state(bot, ctx.group_id)
        except Exception as e:
            logger.debug(
                f"刷新群禁言状态失败: {e}",
                command="AI",
                e=e,
            )

    async def _build_system_prompt(
        self, ctx: ReplyContext, history: list[dict[str, str]]
    ) -> str:
        """构建系统提示词

        使用用户当前激活的人格构建提示词，并注入对应人格的
        情绪状态与记忆，确保人设间数据隔离。

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

        parts = [base_prompt, context_prompt, emotion_prompt, memory_prompt]

        parts.append(context_manager.get_time_flavor_prompt())

        if ctx.group_id:
            try:
                style = await group_profile.get_or_extract_style(
                    ctx.group_id, ctx.text, llm_helper
                )
                style_prompt = build_group_style_prompt_block(style)
                if style_prompt:
                    parts.append(style_prompt)
            except Exception as e:
                logger.debug(
                    f"注入群风格失败: {e}", command="AI", e=e
                )

            # 注入群社交上下文（角色/关系/复读跟随提示）
            if get_config("SOCIAL_INTELLIGENCE_ENABLED", True):
                try:
                    social_prompt = (
                        group_social.build_social_prompt_block(
                            ctx.group_id, ctx.user_id
                        )
                    )
                    if social_prompt:
                        parts.append(social_prompt)
                except Exception as e:
                    logger.debug(
                        f"注入群社交上下文失败: {e}",
                        command="AI",
                        e=e,
                    )

        if get_config("SAFETY_FILTER_ENABLED", True):
            parts.append(build_prompt_injection_guard())

        if (
            ctx.group_id
            and get_config("FRAGMENT_STYLE", "prompt") == "prompt"
        ):
            parts.append(build_group_chat_style_prompt())

        anti_loop = build_anti_loop_hint(history)
        if anti_loop:
            parts.append(anti_loop)

        return "".join(parts)

    async def _load_history(
        self, ctx: ReplyContext
    ) -> list[dict[str, str]]:
        """加载历史对话（带上下文压缩）

        参数:
            ctx: 回复上下文

        返回:
            list[dict]: 历史消息列表（按时间正序）
        """
        try:
            records = await ConversationRecord.get_history(
                ctx.user_id, ctx.group_id,
                limit=get_config("HISTORY_LEN", 20),
                persona_name=ctx.persona_name,
            )
            history = [
                {"role": r.role, "content": r.content}
                for r in reversed(records)
            ]
        except Exception as e:
            logger.debug(
                f"加载历史对话失败: {e}", command="AI", e=e
            )
            return []

        if not history or not get_config("CONTEXT_COMPRESS_ENABLED", True):
            return history

        try:
            chunks = [
                f"{m['role']}: {m.get('content', '')}" for m in history
            ]
            max_tokens = get_config("CONTEXT_MAX_TOKENS", 2000)
            keep_recent = get_config("CONTEXT_KEEP_RECENT", 6)

            async def _call_compress(
                msgs: list[dict[str, str]],
            ) -> str:
                """压缩调用回调

                参数:
                    msgs: 消息列表

                返回:
                    str: LLM返回的摘要
                """
                return await llm_helper.chat_text(msgs)

            compressed_chunks = await compress_context_if_needed(
                chunks,
                max_tokens=max_tokens,
                keep_recent=keep_recent,
                call_ai_api=_call_compress,
            )

            result: list[dict[str, str]] = []
            for chunk in compressed_chunks:
                if chunk.startswith("## 较早上下文摘要"):
                    result.append(
                        {"role": "system", "content": chunk}
                    )
                else:
                    parts = chunk.split(": ", 1)
                    if len(parts) == 2:
                        result.append(
                            {"role": parts[0], "content": parts[1]}
                        )
                    else:
                        result.append({"role": "system", "content": chunk})
            return result
        except Exception as e:
            logger.debug(
                f"上下文压缩失败，降级到原始历史: {e}",
                command="AI",
                e=e,
            )
            return history

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

    async def _generate_reply(
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
            try:
                vp, vm, use_mm = await self._resolve_vision_route(
                    ctx
                )
                if use_mm:
                    vision_provider = vp
                    vision_model = vm
                    use_messages = build_vision_messages(
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
                        ctx.text = (
                            f"{ctx_text}\n[用户附带图片描述: {desc}]"
                            if ctx_text
                            else f"[用户发了一张图片: {desc}]"
                        )
                        use_messages = build_messages(
                            messages[0].get("content", "") if messages else "",
                            [
                                m for m in messages
                                if m.get("role") != "system"
                            ],
                            ctx,
                        )
            except Exception as e:
                logger.warning(
                    f"视觉处理失败，使用原消息: {e}",
                    command="AI",
                    e=e,
                )

        if get_config("AGENT_ENABLED", True):
            try:
                result = await run_agent(
                    use_messages,
                    llm_helper,
                    user_id=ctx.user_id,
                    group_id=ctx.group_id,
                    use_llm_planning=get_config("AGENT_ENABLED", True),
                    persona_name=ctx.persona_name,
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

        if not get_config("SAFETY_FILTER_ENABLED", True):
            try:
                reply_text = await llm_helper.chat_text(
                    use_messages,
                    model=vision_model,
                    provider_name=vision_provider,
                )
                return reply_text, None
            except Exception as e:
                logger.error(
                    f"LLM对话调用失败: {e}", command="AI", e=e
                )
                return random.choice(_FALLBACK_REPLIES), None

        retry_messages = list(use_messages)
        retry_messages.append(
            {
                "role": "system",
                "content": (
                    "\n[重要提示] 请直接以流萤的身份回复，"
                    "不要使用模板化拒绝用语，不要提及自己是AI或助手。"
                    "如果确实无法回答，简短说一句即可。"
                ),
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
                    model=vision_model,
                    provider_name=vision_provider,
                )

            async def _retry_call() -> str:
                """重试LLM调用

                返回:
                    str: LLM回复文本
                """
                return await llm_helper.chat_text(
                    retry_messages,
                    model=vision_model,
                    provider_name=vision_provider,
                )

            reply_text = await sanitize_or_retry(
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

    async def _decide_sticker(
        self,
        text: str,
        ctx: ReplyContext,
        agent_result: AgentResult | None = None,
    ) -> Image | None:
        """贴纸决策

        优先使用 agent_result.response.sticker_mood_hint；
        同时传入 user_id 以便策展器记录偏好。

        参数:
            text: 回复文本
            ctx: 回复上下文
            agent_result: Agent结果（用于提取情绪提示）

        返回:
            Image | None: 贴纸图片对象，不发时返回None
        """
        try:
            persona = await persona_manager.get_user_persona_config(
                ctx.user_id
            )
            persona_mood = persona_manager.get_persona_sticker_mood(
                persona
            )
            mood_hint = ""
            if agent_result and agent_result.response:
                mood_hint = agent_result.response.sticker_mood_hint
            item = await sticker_manager.choose_reply_sticker_item(
                text,
                persona_mood=persona_mood,
                mood_hint=mood_hint,
                group_id=ctx.group_id,
                is_private=ctx.is_private,
                user_id=ctx.user_id,
            )
            if not item:
                return None
            # 记录使用，便于反馈学习
            await sticker_manager.record_usage(
                sticker_id=item.id,
                context_text=text,
                detected_mood=mood_hint or persona_mood,
                persona_mood=persona_mood,
                group_id=ctx.group_id or "",
                user_id=ctx.user_id,
                bot_id=ctx.bot_id or "",
            )
            return await sticker_manager.item_to_image(item)
        except Exception as e:
            logger.debug(
                f"贴纸决策失败: {e}", command="AI", e=e
            )
            return None

    async def _decide_tts(
        self, text: str, ctx: ReplyContext
    ) -> bytes | None:
        """TTS决策（占位）

        阶段4实现完整TTS服务。

        参数:
            text: 回复文本
            ctx: 回复上下文

        返回:
            bytes | None: 音频数据，不发时返回None
        """
        if not get_config("TTS_ENABLED", False) or not get_config(
            "TTS_AUTO_ENABLED", False
        ):
            return None
        if len(text) < _TTS_AUTO_TEXT_MIN_LEN:
            return None

        if random.random() >= get_config("TTS_AUTO_PROBABILITY", 0.2):
            return None
        try:
            persona = await persona_manager.get_user_persona_config(
                ctx.user_id
            )
            tts_config = persona_manager.get_persona_tts_config(persona)
            voice = tts_config.get("voice", get_config("TTS_VOICE", "alloy"))
            return await llm_helper.tts(text, voice=voice)
        except Exception as e:
            logger.debug(
                f"TTS决策失败: {e}", command="AI", e=e
            )
            return None

    async def handle(self, ctx: ReplyContext) -> ReplyResult:
        """主入口：处理用户消息并生成回复

        在权限检查通过后，先解析用户当前激活的bot人格名，
        写入 ctx.persona_name 供后续所有数据操作隔离使用。

        本方法还集成用户对话 token 额度：
        - 对话前检查额度，不足则阻止对话并（满足 CD 时）
          返回额度不足提示；
        - 对话周期内通过会话级用量累加器统计实际 token 消耗；
        - 对话结束后按实际消耗扣费。

        参数:
            ctx: 回复上下文

        返回:
            ReplyResult: 回复结果
        """
        start_time = time.time()

        if not await self._check_permission(ctx):
            return ReplyResult(text="", typing_delay=0.0)

        # 用户对话 token 额度检查（不足则阻止对话继续）
        quota = await token_quota_service.check_before_conversation(
            ctx.user_id
        )
        if not quota.allowed:
            logger.info(
                f"用户对话额度不足，跳过回复: "
                f"user={ctx.user_id} group={ctx.group_id or ''} "
                f"reason={quota.reason}",
                command="AI",
            )
            if quota.need_remind:
                tip = _QUOTA_INSUFFICIENT_TPL.format(
                    remaining=max(0, quota.remaining)
                )
                return ReplyResult(
                    text=tip,
                    metadata={
                        "quota_blocked": True,
                        "remaining": quota.remaining,
                        "elapsed": round(time.time() - start_time, 3),
                    },
                )
            # CD 期内不重复提醒，静默跳过
            return ReplyResult(
                text="",
                metadata={
                    "quota_blocked": True,
                    "silence": True,
                    "remaining": quota.remaining,
                    "elapsed": round(time.time() - start_time, 3),
                },
            )

        # 解析用户当前激活的人格名，确保人设间数据隔离
        try:
            ctx.persona_name = await persona_manager.get_user_persona_name(
                ctx.user_id
            )
        except Exception as e:
            logger.debug(
                f"获取用户人格失败，回退默认: {e}",
                command="AI",
                e=e,
            )

        history = await self._load_history(ctx)
        system_prompt = await self._build_system_prompt(ctx, history)
        messages = build_messages(system_prompt, history, ctx)

        # 开启会话级 token 用量追踪，统计本轮所有 LLM 调用消耗
        track_token = start_conversation_tracking()
        try:
            reply_text, agent_result = await self._generate_reply(
                messages, ctx
            )
        finally:
            usage = stop_conversation_tracking(track_token)

        # 按实际消耗扣费（失败不影响已生成回复的发送）
        try:
            await token_quota_service.consume_after_conversation(
                ctx.user_id, usage
            )
        except Exception as e:
            logger.debug(
                f"用户额度扣费失败（不影响回复）: {e}",
                command="AI",
                e=e,
            )

        if has_silence_control_marker(reply_text):
            logger.info(
                f"AI决定SILENCE，跳过回复: user={ctx.user_id} "
                f"group={ctx.group_id}",
                command="AI",
            )
            return ReplyResult(
                text="",
                metadata={
                    "silence": True,
                    "elapsed": round(time.time() - start_time, 3),
                    "token_usage": usage,
                },
            )

        elapsed = time.time() - start_time
        humanized_text, typing_delay = humanize_reply(
            reply_text, elapsed, ctx
        )

        if not humanized_text:
            return ReplyResult(
                text="",
                typing_delay=0.0,
                metadata={
                    "elapsed": round(elapsed, 3),
                    "token_usage": usage,
                },
            )

        segments, gap_delays = build_segments(
            humanized_text, ctx
        )

        sticker_task = asyncio.create_task(
            self._decide_sticker(humanized_text, ctx, agent_result)
        )
        tts_task = asyncio.create_task(
            self._decide_tts(humanized_text, ctx)
        )
        persist_task = asyncio.create_task(
            persist_conversation(
                ctx, ctx.text, humanized_text, agent_result, elapsed
            )
        )

        sticker_path = await sticker_task
        tts_audio = await tts_task
        await persist_task

        metadata: dict[str, Any] = {
            "elapsed": round(elapsed, 3),
            "history_count": len(history),
            "segment_count": len(segments),
            "token_usage": usage,
        }
        if agent_result and agent_result.tool_calls:
            metadata["tool_calls"] = agent_result.tool_calls
            metadata["agent_steps"] = agent_result.steps

        return ReplyResult(
            text=humanized_text,
            segments=segments,
            sticker=sticker_path,
            tts_audio=tts_audio,
            image_url=agent_result.image_url if agent_result else None,
            typing_delay=typing_delay,
            gap_delays=gap_delays,
            tool_calls=(
                agent_result.tool_calls
                if agent_result
                else []
            ),
            metadata=metadata,
        )

    async def handle_text(
        self,
        user_id: str,
        text: str,
        group_id: str | None = None,
        platform: str | None = None,
        bot_id: str | None = None,
        is_at_bot: bool = False,
        is_private: bool = False,
        image_data: bytes | None = None,
        image_mime: str = "image/jpeg",
        persona_name: str = "default",
    ) -> ReplyResult:
        """便捷入口：通过参数构造上下文处理回复

        参数:
            user_id: 用户ID
            text: 用户消息文本
            group_id: 群组ID
            platform: 平台名
            bot_id: 机器人ID
            is_at_bot: 是否@机器人
            is_private: 是否私聊
            image_data: 图片二进制数据，None表示无图片
            image_mime: 图片MIME类型，默认image/jpeg
            persona_name: bot人格名，default时由handle内解析

        返回:
            ReplyResult: 回复结果
        """
        ctx = ReplyContext(
            user_id=user_id,
            group_id=group_id,
            platform=platform,
            bot_id=bot_id,
            text=text,
            is_at_bot=is_at_bot,
            is_private=is_private,
            image_data=image_data,
            image_mime=image_mime,
            persona_name=persona_name,
        )
        return await self.handle(ctx)


reply_processor = ReplyProcessor()
"""回复处理器单例"""
