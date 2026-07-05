"""上下文策略

提供 SILENCE 控制标记识别与剥离、token 估算与历史压缩、
anti-loop 检测与提示注入。
"""

from collections.abc import Awaitable, Callable
import re
from typing import Any

__all__ = ["ContextPolicy"]


_SILENCE_MARKERS: tuple[str, ...] = (
    "[SILENCE]",
    "<SILENCE>",
    "[NO_REPLY]",
    "<NO_REPLY>",
)
"""SILENCE 控制标记元组"""


_SILENCE_BARE_WORDS: frozenset[str] = frozenset({
    "silence",
    "silent",
    "no_reply",
    "no-reply",
    "noreply",
    "沉默",
    "不回复",
    "无回复",
    "静默",
    "保持沉默",
})
"""裸词识别集合"""


_SILENCE_PREFIX_PATTERN = re.compile(
    r"^\s*(?:silence|silent|no[_\s\-]?reply|noreply|沉默|不回复|无回复|静默|保持沉默)\s*[:：]\s*",
    re.IGNORECASE,
)
"""SILENCE 前缀模式（如 "SILENCE:" / "沉默："）"""


_SILENCE_LEADING_LINE_PATTERN = re.compile(
    r"^\s*(?:\[SILENCE\]|<SILENCE>|\[NO_REPLY\]|<NO_REPLY>)\s*\n?",
    re.IGNORECASE,
)
"""行首SILENCE标记模式"""


_THINK_BLOCK_PATTERN = re.compile(
    r"<\s*(?:think|status|action)\b[^>]*>.*?</\s*(?:think|status|action)\s*>",
    re.IGNORECASE | re.DOTALL,
)
"""完整闭合的思维链块模式"""


_THINK_OPEN_PATTERN = re.compile(
    r"<\s*(?:think|status|action)\b[^>]*>[\s\S]*?(?=<\s*[A-Za-z/]|\Z)",
    re.IGNORECASE,
)
"""未闭合的思维链块模式"""


_TAG_RESIDUE_PATTERN = re.compile(
    r"</?\s*(?:output|message|think|status|action)\b[^>]*>",
    re.IGNORECASE,
)
"""残留标签模式"""


_COMPRESS_SYSTEM_PROMPT = (
    "请将较早对话上下文压缩成 1-2 句中文摘要。"
    "保留人物关系、话题延续、已确认事实和未完成事项。"
    "直接输出摘要，不要列表，不要解释。"
)
"""压缩时的系统提示词"""


class ContextPolicy:
    """上下文策略集合

    集中管理 SILENCE 控制标记识别、响应清理、token 估算、
    历史压缩与 anti-loop 检测等上下文相关策略。
    """

    @staticmethod
    def has_silence_control_marker(text: Any) -> bool:
        """检测文本是否包含 SILENCE 控制标记

        参数:
            text: 待检测文本

        返回:
            bool: 是否包含SILENCE标记
        """
        raw = str(text or "")
        if any(marker in raw for marker in _SILENCE_MARKERS):
            return True

        stripped = raw.strip()
        if not stripped:
            return False

        if stripped.lower() in _SILENCE_BARE_WORDS:
            return True

        if _SILENCE_PREFIX_PATTERN.match(stripped):
            leftover = _SILENCE_PREFIX_PATTERN.sub("", stripped, count=1).strip()
            if not leftover:
                return True

        return False

    @staticmethod
    def strip_response_control_markers(text: Any) -> str:
        """剥离响应中的控制标记和思维链块

        参数:
            text: 原始响应文本

        返回:
            str: 清理后的文本
        """
        cleaned = str(text or "")

        cleaned = _THINK_BLOCK_PATTERN.sub("", cleaned)
        cleaned = _THINK_OPEN_PATTERN.sub("", cleaned)
        cleaned = _TAG_RESIDUE_PATTERN.sub("", cleaned)

        for marker in _SILENCE_MARKERS:
            cleaned = cleaned.replace(marker, "")

        cleaned = _SILENCE_LEADING_LINE_PATTERN.sub("", cleaned, count=1)
        cleaned = _SILENCE_PREFIX_PATTERN.sub("", cleaned, count=1)

        bare = cleaned.strip()
        if bare.lower() in _SILENCE_BARE_WORDS:
            return ""
        return bare

    @staticmethod
    def estimate_chunk_tokens(text: str) -> int:
        """估算文本的token数

        中文按1.5 token/字，英文按4字符1token估算。

        参数:
            text: 待估算文本

        返回:
            int: 估算的token数
        """
        raw = str(text or "")
        cjk_chars = sum(1 for ch in raw if "\u4e00" <= ch <= "\u9fff")
        other_chars = max(0, len(raw) - cjk_chars)
        return int(cjk_chars * 1.5 + other_chars / 4) + 1

    @staticmethod
    def _estimate_chunks_tokens(chunks: list[str]) -> int:
        """估算多个chunk的总token数

        参数:
            chunks: 文本块列表

        返回:
            int: 总token数
        """
        return sum(ContextPolicy.estimate_chunk_tokens(c) for c in chunks)

    @staticmethod
    async def compress_context_if_needed(
        chunks: list[str],
        max_tokens: int = 2000,
        *,
        keep_recent: int = 6,
        call_ai_api: Callable[[list[dict[str, str]]], Awaitable[str]] | None = None,
    ) -> list[str]:
        """超过token预算时压缩早期上下文为摘要

        参数:
            chunks: 上下文块列表
            max_tokens: 最大token预算
            keep_recent: 保留最近N条不压缩
            call_ai_api: LLM调用函数，None时不调用LLM直接截断

        返回:
            list[str]: 压缩后的块列表
        """
        normalized = [str(c or "").strip() for c in chunks if str(c or "").strip()]
        if ContextPolicy._estimate_chunks_tokens(normalized) <= max_tokens:
            return normalized

        keep_recent = max(1, min(int(keep_recent or 0), len(normalized)))
        earlier_chunks = normalized[:-keep_recent]
        recent_chunks = normalized[-keep_recent:]

        summary_chunk = ""
        if earlier_chunks:
            if call_ai_api is not None:
                try:
                    raw_summary = await call_ai_api([
                        {"role": "system", "content": _COMPRESS_SYSTEM_PROMPT},
                        {"role": "user", "content": "\n\n".join(earlier_chunks)},
                    ])
                    summary_text = (raw_summary or "").strip()
                except Exception:
                    summary_text = ""
            else:
                summary_text = earlier_chunks[-1][:200]

            max_summary_tokens = max(64, max_tokens // 4)
            while (
                summary_text
                and ContextPolicy.estimate_chunk_tokens(summary_text)
                > max_summary_tokens
            ):
                summary_text = summary_text[: int(len(summary_text) * 0.7)]
                summary_text = summary_text.rsplit("。", 1)[0]
                if not summary_text:
                    break

            if summary_text:
                summary_chunk = f"## 较早上下文摘要\n{summary_text}"

        compressed = (
            [summary_chunk, *recent_chunks] if summary_chunk else list(recent_chunks)
        )

        while (
            ContextPolicy._estimate_chunks_tokens(compressed) > max_tokens
            and len(compressed) > 1
        ):
            compressed.pop(0)

        return compressed

    @staticmethod
    def _token_similarity(a: str, b: str) -> float:
        """计算两段文本的token级Jaccard相似度

        参数:
            a: 文本A
            b: 文本B

        返回:
            float: 相似度[0,1]
        """
        set_a = set(a)
        set_b = set(b)
        if not set_a or not set_b:
            return 0.0
        intersection = set_a & set_b
        union = set_a | set_b
        return len(intersection) / len(union) if union else 0.0

    @staticmethod
    def build_anti_loop_hint(history: list[dict[str, str]]) -> str:
        """检测重复话题并返回 anti-loop 提示

        参数:
            history: 历史消息列表

        返回:
            str: anti-loop 提示文本，无重复时返回空串
        """
        if len(history) < 3:
            return ""

        user_texts = [
            (m.get("content") or "")
            for m in history
            if m.get("role") == "user"
        ]
        assistant_texts = [
            (m.get("content") or "")
            for m in history
            if m.get("role") == "assistant"
        ]

        if len(user_texts) < 2 or len(assistant_texts) < 2:
            return ""

        repeated_user = user_texts[-1] and user_texts[-1] == user_texts[-2]
        repeated_assistant = (
            len(assistant_texts) >= 2
            and assistant_texts[-1] == assistant_texts[-2]
        )
        repetitive_similarity = False
        if len(assistant_texts) >= 3:
            sims = [
                ContextPolicy._token_similarity(
                    assistant_texts[-1], assistant_texts[-2]
                ),
                ContextPolicy._token_similarity(
                    assistant_texts[-2], assistant_texts[-3]
                ),
            ]
            repetitive_similarity = all(s >= 0.6 for s in sims)

        if not repeated_user and not repeated_assistant and not repetitive_similarity:
            return ""

        return (
            "\n\n[Anti-loop guard]（高优先级）\n"
            "- 最近几轮对话出现重复话题。\n"
            "- 优先关注最新用户输入，避免重复旧观点。\n"
            "- 若无新信息可说，回复不超过12个中文字符或输出 [SILENCE]。\n"
        )
