"""回复处理主流程

整合权限检查、群禁言感知、人格管理、记忆召回、上下文压缩、
Agent循环、安全过滤、拟人化处理、贴纸决策、碎片化分段、
持久化等环节，构建完整的对话回复流水线。

提示词组装委托给 PromptBuilder，回复生成委托给 ReplyGenerator。
"""

import asyncio
import time
from typing import Any

from liuying.utils.log import logger

from ..agent.agent.learning import active_learning
from ..config import get_config
from ..core.context import ContextPolicy
from ..core.group import GroupMuteTracker
from ..core.llm import (
    TokenTrackingHelper,
    llm_helper,
)
from ..core.llm.model_router import ROLE_INTENT, model_router
from ..core.peer_awareness import peer_awareness
from ..core.persona import persona_manager
from ..core.reply_turn_trace import reply_turn_trace
from ..core.safety import token_quota_service
from ..models.conversation_record import ConversationRecord
from .decisions import ReplyDecisions
from .helpers import ReplyPipeline
from .humanize import HumanizeToolkit
from .prompt_builder import PromptBuilder
from .reply_generator import ReplyGenerator
from .response_review import response_reviewer
from .text_policy import ReplyTextPolicy
from .types import ReplyContext, ReplyResult


class ReplyProcessor:
    """回复处理器

    整合所有core服务和pipeline组件，编排完整的对话回复流程。
    提示词构建委托给 PromptBuilder，回复生成委托给 ReplyGenerator。
    """

    def __init__(self) -> None:
        """初始化回复处理器"""
        self._prompt_builder = PromptBuilder()
        self._reply_generator = ReplyGenerator()

    async def _check_permission(
        self, ctx: ReplyContext
    ) -> bool:
        """权限检查（群禁言感知与环境感知）

        用户/群组黑名单（ban）已由流萤本体 hooks/auth_ban 统一拦截，
        此处仅处理AI私有的禁言感知与peer感知。

        参数:
            ctx: 回复上下文

        返回:
            bool: 是否允许回复
        """
        if ctx.group_id and get_config("GROUP_MUTE_AWARE", True):
            if GroupMuteTracker.is_group_muted(ctx.group_id):
                logger.info(
                    f"群 {ctx.group_id} bot处于禁言期，本轮跳过回复",
                    command="AI",
                    group_id=ctx.group_id,
                )
                return False

        # 环境感知：检测到其他bot发言后触发静默，避免bot互相对话
        if (
            ctx.group_id
            and get_config("PEER_AWARENESS_ENABLED", True)
            and peer_awareness.should_silence(ctx.group_id)
        ):
            logger.debug(
                f"群 {ctx.group_id} 处于peer静默期，跳过回复",
                command="AI",
                group_id=ctx.group_id,
            )
            return False

        return True

    async def _load_history(
        self, ctx: ReplyContext
    ) -> list[dict[str, str]]:
        """加载历史对话（带上下文压缩）

        参数:
            ctx: 回复上下文

        返回:
            list[dict]: 历史消息列表（按时间正序）
        """
        records = await ConversationRecord.get_history(
            ctx.user_id, ctx.group_id,
            limit=get_config("HISTORY_LEN", 20),
            persona_name=ctx.persona_name,
        )
        history = [
            {"role": r.role, "content": r.content}
            for r in reversed(records)
        ]

        compress_cfg = get_config("CONTEXT_COMPRESS", {})
        if not history or not compress_cfg.get("enabled", True):
            return history

        try:
            chunks = [
                f"{m['role']}: {m.get('content', '')}" for m in history
            ]
            max_tokens = compress_cfg.get("max_tokens", 2000)
            keep_recent = compress_cfg.get("keep_recent", 6)

            async def _call_compress(
                msgs: list[dict[str, str]],
            ) -> str:
                """压缩调用回调

                参数:
                    msgs: 消息列表

                返回:
                    str: LLM返回的摘要
                """
                role = model_router.resolve(ROLE_INTENT)
                return await llm_helper.chat_text(
                    msgs,
                    model=role.model or None,
                    options=role.apply_to_options(),
                    provider_name=role.provider or None,
                )

            compressed_chunks = await ContextPolicy.compress_context_if_needed(
                chunks,
                max_tokens=max_tokens,
                keep_recent=keep_recent,
                call_ai_api=_call_compress,
            )

            return ContextPolicy.parse_compressed_chunks(
                compressed_chunks
            )
        except Exception as e:
            logger.debug(
                f"上下文压缩失败，降级到原始历史: {e}",
                command="AI",
                e=e,
            )
            return history

    async def handle(self, ctx: ReplyContext) -> ReplyResult:
        """主入口：处理用户消息并生成回复

        在权限检查通过后，先解析用户当前激活的bot人格名，
        写入 ctx.persona_name 供后续所有数据操作隔离使用。

        本方法还集成用户对话 token 额度：
        - 对话前检查额度，不足则阻止对话并（满足 CD 时）
          返回额度不足提示；
        - 对话周期内通过会话级用量累加器统计实际 token 消耗；
        - 对话结束后按实际消耗扣费。

        本方法同时通过 reply_turn_trace 记录各阶段耗时与状态，
        用于事后诊断回复异常。

        参数:
            ctx: 回复上下文

        返回:
            ReplyResult: 回复结果
        """
        start_time = time.time()
        session_type = "private" if ctx.is_private else "group"
        trace_id = reply_turn_trace.start_trace(
            session_type=session_type,
            group_id=ctx.group_id or "",
            user_id=ctx.user_id,
        )

        if not await self._check_permission(ctx):
            reply_turn_trace.finish_trace(
                trace_id=trace_id,
                outcome="permission_denied",
            )
            return ReplyResult(text="", typing_delay=0.0)
        reply_turn_trace.record_stage(
            trace_id=trace_id, key="permission", label="权限检查通过"
        )

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
            reply_turn_trace.finish_trace(
                trace_id=trace_id,
                outcome="quota_blocked",
                diagnosis_code=quota.reason,
            )
            if quota.need_remind:
                tip = (
                    f"咦？你的token似乎不足捏（剩余 {max(0, quota.remaining)} token），"
                    "去兑换铜币再试试看~"
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
        reply_turn_trace.record_stage(
            trace_id=trace_id,
            key="quota_check",
            label="额度检查通过",
        )

        # 解析用户当前激活的人格名，确保人设间数据隔离
        # get_user_persona_name 内部已捕获异常并回退默认人格，无需外层兜底
        ctx.persona_name = await persona_manager.get_user_persona_name(
            ctx.user_id
        )

        history = await self._load_history(ctx)
        reply_turn_trace.record_stage(
            trace_id=trace_id,
            key="load_history",
            label=f"加载历史{len(history)}条",
        )
        system_prompt = await self._prompt_builder.build_system_prompt(
            ctx, history
        )
        reply_turn_trace.record_stage(
            trace_id=trace_id, key="build_prompt", label="构建提示词完成"
        )
        messages = ReplyPipeline.build_messages(
            system_prompt, history, ctx
        )

        # 开启会话级 token 用量追踪，统计本轮所有 LLM 调用消耗
        track_token = TokenTrackingHelper.start_conversation_tracking()
        try:
            reply_text, agent_result = await self._reply_generator.generate_reply(
                messages, ctx
            )
        finally:
            usage = TokenTrackingHelper.stop_conversation_tracking(
                track_token
            )
        reply_turn_trace.record_stage(
            trace_id=trace_id,
            key="generate_reply",
            label="生成回复完成",
            detail=f"长度={len(reply_text)}",
        )

        # 回复文本为空（静默建议/LLM空输出）时记录诊断日志，
        # 避免"无回复且无报错"现象无法追踪根因
        if not reply_text.strip():
            suggest_silence = bool(
                agent_result
                and agent_result.response
                and agent_result.response.recommend_silence
            )
            logger.warning(
                f"回复文本为空: user={ctx.user_id} "
                f"group={ctx.group_id or ''} "
                f"suggest_silence={suggest_silence}",
                command="AI",
            )

        # 按实际消耗扣费（内部已处理异常，失败不影响已生成回复的发送）
        await token_quota_service.consume_after_conversation(
            ctx.user_id, usage
        )

        # 响应深度审查：LLM二次审核回复质量与安全
        review = await response_reviewer.review(
            user_message=ctx.text,
            reply_text=reply_text,
        )
        if review.final_text != reply_text:
            logger.debug(
                f"响应审查调整回复: verdict={review.verdict} "
                f"reason={review.reason}",
                command="AI",
            )
            reply_text = review.final_text
        reply_turn_trace.record_stage(
            trace_id=trace_id,
            key="review",
            label=f"审查verdict={review.verdict}",
        )

        # 回复文本策略：清理Markdown格式，让回复像真人而非文档
        reply_text = ReplyTextPolicy.normalize_visible_reply_text(
            reply_text
        )

        if ContextPolicy.has_silence_control_marker(reply_text):
            logger.info(
                f"AI决定SILENCE，跳过回复: user={ctx.user_id} "
                f"group={ctx.group_id}",
                command="AI",
            )
            # 主动学习：即使SILENCE也异步分析不确定性（fire-and-forget）
            active_learning.process_reply_async(
                user_id=ctx.user_id,
                user_question=ctx.text,
                ai_reply=reply_text,
                persona_name=ctx.persona_name,
            )
            reply_turn_trace.finish_trace(
                trace_id=trace_id, outcome="silence"
            )
            # 沉默时按概率表情表态（仅群聊，由发送方拿到message_id后执行）
            react_face_id = ReplyDecisions.decide_silence_reaction(ctx)
            return ReplyResult(
                text="",
                react_face_id=react_face_id,
                metadata={
                    "silence": True,
                    "elapsed": round(time.time() - start_time, 3),
                    "token_usage": usage,
                },
            )

        # 主动学习：异步分析回复中的不确定性并深度查证（fire-and-forget）
        active_learning.process_reply_async(
            user_id=ctx.user_id,
            user_question=ctx.text,
            ai_reply=reply_text,
            persona_name=ctx.persona_name,
        )

        elapsed = time.time() - start_time
        humanized_text, typing_delay = ReplyPipeline.humanize_reply(
            reply_text, elapsed, ctx
        )

        if not humanized_text:
            reply_turn_trace.finish_trace(
                trace_id=trace_id, outcome="empty_reply"
            )
            return ReplyResult(
                text="",
                typing_delay=0.0,
                metadata={
                    "elapsed": round(elapsed, 3),
                    "token_usage": usage,
                },
            )
        reply_turn_trace.record_stage(
            trace_id=trace_id, key="humanize", label="拟人化完成"
        )

        # 用户人格配置取一次后透传，避免贴纸/TTS/口头禅重复获取
        persona = await persona_manager.get_user_persona_config(
            ctx.user_id
        )

        # 口头禅运行时插入：从人格catchphrase按概率前置
        humanized_text = await ReplyDecisions.maybe_prepend_catchphrase(
            humanized_text, ctx, persona
        )

        segments, gap_delays = ReplyPipeline.build_segments(
            humanized_text, ctx
        )

        # 拟人化协议扩展决策：输入状态/引用回复/@回复
        should_set_typing = ReplyDecisions.decide_typing_status(
            ctx, typing_delay
        )
        should_quote = HumanizeToolkit.should_quote_reply(
            is_private=ctx.is_private,
            quote_enabled=get_config("QUOTE_REPLY_ENABLED", True),
            history_len=len(history),
        )
        at_user_id = (
            ctx.user_id
            if HumanizeToolkit.should_at_target(
                is_private=ctx.is_private,
                at_enabled=get_config("AT_REPLY_ENABLED", True),
                is_at_bot=ctx.is_at_bot,
                should_quote=should_quote,
            )
            else None
        )

        # 并行执行贴纸决策、TTS决策与持久化
        # gather确保任一协程异常时取消其他任务，避免悬挂任务
        sticker_path, tts_audio, _ = await asyncio.gather(
            ReplyDecisions.decide_sticker(
                humanized_text, ctx, persona, agent_result
            ),
            ReplyDecisions.decide_tts(humanized_text, ctx, persona),
            ReplyPipeline.persist_conversation(
                ctx, ctx.text, humanized_text, agent_result, elapsed
            ),
        )

        metadata: dict[str, Any] = {
            "elapsed": round(elapsed, 3),
            "history_count": len(history),
            "segment_count": len(segments),
            "token_usage": usage,
            "trace_id": trace_id,
        }
        if agent_result and agent_result.tool_calls:
            metadata["tool_calls"] = agent_result.tool_calls
            metadata["agent_steps"] = agent_result.steps

        reply_turn_trace.finish_trace(
            trace_id=trace_id,
            outcome="success",
            detail={
                "elapsed": round(elapsed, 3),
                "segments": len(segments),
            },
        )
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
            should_set_typing=should_set_typing,
            should_quote=should_quote,
            at_user_id=at_user_id,
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
    ) -> ReplyResult:
        """便捷入口：通过参数构造上下文处理回复

        人格名由 handle 内统一解析并覆盖，不在此传入。

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
        )
        return await self.handle(ctx)


reply_processor = ReplyProcessor()
"""回复处理器单例"""
