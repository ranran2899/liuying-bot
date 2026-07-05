"""回复处理辅助函数

提供消息构建、拟人化处理、碎片化分段、持久化等辅助功能。
"""

import asyncio
import base64
import json
from typing import Any

from liuying.utils.log import logger

from ..agent.runner import AgentResult
from ..config import get_config
from ..core.context import ContextPolicy, context_manager
from ..core.emotion import emotion_manager
from ..core.memory import memory_manager
from ..models.conversation_record import ConversationRecord
from .humanize import (
    compute_gap_delay,
    compute_typing_delay,
    fragment_reply,
    maybe_inject_typo,
)
from .types import ReplyContext

__all__ = ["ReplyPipeline", "reply_pipeline"]


class ReplyPipeline:
    """回复处理辅助管线

    封装消息构建、多模态消息构建、拟人化处理、碎片化分段
    与持久化等能力，所有方法均为静态方法。
    """

    @staticmethod
    def build_messages(
        system_prompt: str,
        history: list[dict[str, str]],
        ctx: ReplyContext,
    ) -> list[dict[str, str]]:
        """构建完整消息列表

        参数:
            system_prompt: 系统提示词
            history: 历史消息
            ctx: 回复上下文

        返回:
            list[dict]: 完整消息列表
        """
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]
        messages.extend(history)
        messages.append(
            {"role": "user", "content": ctx.text}
        )
        return messages

    @staticmethod
    def build_vision_messages(
        system_prompt: str,
        history: list[dict[str, str]],
        ctx: ReplyContext,
    ) -> list[dict[str, Any]]:
        """构建带图片的多模态消息列表

        参数:
            system_prompt: 系统提示词
            history: 历史消息
            ctx: 回复上下文（含图片数据）

        返回:
            list[dict]: 多模态消息列表
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]
        messages.extend(history)

        b64 = base64.b64encode(
            ctx.image_data or b""
        ).decode("ascii")
        data_url = f"data:{ctx.image_mime};base64,{b64}"
        user_content: list[dict[str, Any]] = [
            {"type": "text", "text": ctx.text or "请描述这张图片"},
            {
                "type": "image_url",
                "image_url": {"url": data_url},
            },
        ]
        messages.append({"role": "user", "content": user_content})
        return messages

    @staticmethod
    def humanize_reply(
        text: str, elapsed: float, ctx: ReplyContext
    ) -> tuple[str, float]:
        """拟人化处理

        参数:
            text: 原始回复文本
            elapsed: LLM生成耗时
            ctx: 回复上下文

        返回:
            tuple[str, float]: (处理后文本, 打字延迟)
        """
        text = ContextPolicy.strip_response_control_markers(text)
        if not text:
            return text, 0.0

        text, _correction = maybe_inject_typo(
            text, get_config("HUMANIZE_TYPO_PROBABILITY", 0.0)
        )

        typing_delay = 0.0
        if get_config("HUMANIZE_TYPING_ENABLED", True):
            is_night = context_manager.is_night_time()
            typing_delay = compute_typing_delay(
                text,
                cps=get_config("HUMANIZE_TYPING_CPS", 7.0),
                max_delay=get_config(
                    "HUMANIZE_TYPING_MAX_DELAY", 5.0
                ),
                already_elapsed=elapsed,
                is_night=is_night,
            )

        return text, typing_delay

    @staticmethod
    def build_segments(
        text: str, ctx: ReplyContext
    ) -> tuple[list[str], list[float]]:
        """构建碎片化段列表与段间延迟

        参数:
            text: 拟人化后的回复文本
            ctx: 回复上下文

        返回:
            tuple[list[str], list[float]]: (段列表, 段间延迟列表)
        """
        if not text:
            return [], []

        if (
            not ctx.group_id
            or get_config("FRAGMENT_STYLE", "prompt") == "off"
        ):
            return [text], []

        max_chars = get_config("FRAGMENT_MAX_CHARS", 40)
        segments = fragment_reply(text, max_segment_chars=max_chars)
        if len(segments) <= 1:
            return [text], []

        gap_delays: list[float] = []
        for i in range(len(segments) - 1):
            gap = compute_gap_delay(segments[i + 1])
            gap_delays.append(gap)
        gap_delays.append(0.0)

        return segments, gap_delays

    @staticmethod
    async def persist_conversation(
        ctx: ReplyContext,
        user_text: str,
        reply_text: str,
        agent_result: AgentResult | None,
        elapsed: float,
    ) -> None:
        """持久化对话记录、情绪、记忆（三路并行）

        将记录写入、情绪更新、记忆添加三个独立任务并行执行，
        避免串行 await 累加耗时。单任务失败不影响其他任务。

        参数:
            ctx: 回复上下文
            user_text: 用户消息
            reply_text: AI回复
            agent_result: Agent结果
            elapsed: 总耗时
        """
        metadata: dict[str, Any] = {}
        if agent_result and agent_result.tool_calls:
            metadata["tool_calls"] = agent_result.tool_calls
        metadata["elapsed"] = round(elapsed, 3)
        metadata_json = json.dumps(metadata, ensure_ascii=False)

        async def _persist_records() -> None:
            """顺序写入用户和助手对话记录（保持时间顺序）"""
            await ConversationRecord.add_record(
                user_id=ctx.user_id,
                role="user",
                content=user_text,
                group_id=ctx.group_id,
                bot_id=ctx.bot_id,
                platform=ctx.platform,
                persona_name=ctx.persona_name,
            )
            await ConversationRecord.add_record(
                user_id=ctx.user_id,
                role="assistant",
                content=reply_text,
                group_id=ctx.group_id,
                bot_id=ctx.bot_id,
                platform=ctx.platform,
                metadata_json=metadata_json,
                persona_name=ctx.persona_name,
            )

        async def _safe(
            task: Any, name: str, level: str = "debug"
        ) -> None:
            """安全执行子任务并记录异常

            参数:
                task: 子任务协程
                name: 任务名（用于日志）
                level: 日志级别（warning/debug）
            """
            try:
                await task
            except Exception as e:
                log_fn = (
                    logger.warning
                    if level == "warning"
                    else logger.debug
                )
                log_fn(
                    f"{name}失败: {e}", command="AI", e=e
                )

        memory_task = (
            memory_manager.add(
                user_id=ctx.user_id,
                content=f"用户: {user_text}\nAI: {reply_text}",
                summary=reply_text[:100],
                group_id=ctx.group_id,
                tier="working",
                persona_name=ctx.persona_name,
            )
            if get_config("MEMORY_ENABLED", True)
            else asyncio.sleep(0)
        )

        await asyncio.gather(
            _safe(_persist_records(), "持久化对话记录", "warning"),
            _safe(
                emotion_manager.update_after_chat(
                    ctx.user_id,
                    ctx.group_id,
                    [
                        {"role": "user", "content": user_text},
                        {"role": "assistant", "content": reply_text},
                    ],
                    persona_name=ctx.persona_name,
                ),
                "更新情绪状态",
            ),
            _safe(memory_task, "添加记忆"),
        )


reply_pipeline = ReplyPipeline()
"""回复处理辅助管线单例"""
