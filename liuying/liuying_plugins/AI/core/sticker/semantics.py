"""贴纸语义分析

基于 LLM 分析用户消息的情感语义，匹配贴纸标签，
为贴纸选择提供更细粒度的语义匹配能力。
"""

import json
from typing import Any

from liuying.utils.log import logger

from ...config import get_config
from ..llm import llm_helper

__all__ = ["StickerSemantics", "sticker_semantics"]


_ANALYZE_PROMPT = """请分析下面用户消息的情感语义，并匹配适合的贴纸标签。
按JSON格式返回，字段：
- mood: 主要情绪（happy/sad/excited/angry/shy/calm/warm/playful/greet/bye/neutral之一）
- semantic_tags: 语义标签数组（greet/bye/thanks/apology/ridicule/encourage/love等）
- intent: 意图简述（不超过10字）
- confidence: 置信度（0-1之间浮点）

用户消息：{text}
只返回JSON。"""
"""语义分析prompt"""


_FALLBACK_RESULT: dict[str, Any] = {
    "mood": "neutral",
    "semantic_tags": [],
    "intent": "",
    "confidence": 0.0,
}
"""分析失败时的兜底结果"""


class StickerSemantics:
    """贴纸语义分析器

    使用 LLM 分析用户消息的情感、意图与语义标签，
    输出结构化结果供贴纸选择策略使用。
    """

    def __init__(self) -> None:
        """初始化贴纸语义分析器"""

    def _is_enabled(self) -> bool:
        """检查语义分析是否启用

        返回:
            bool: 是否启用
        """
        return bool(get_config("STICKER_SEMANTIC_ENABLED", True))

    def _build_prompt(self, text: str) -> str:
        """构建分析prompt

        参数:
            text: 用户消息文本

        返回:
            str: 完整prompt
        """
        safe_text = text[:200] if text else ""
        return _ANALYZE_PROMPT.format(text=safe_text)

    def _parse_response(self, response: str) -> dict[str, Any]:
        """解析LLM返回的JSON结果

        参数:
            response: LLM响应文本

        返回:
            dict: 解析后的结构化结果
        """
        if not response:
            return dict(_FALLBACK_RESULT)
        try:
            data = json.loads(response.strip())
        except (json.JSONDecodeError, ValueError) as e:
            logger.debug(
                f"语义分析响应解析失败: {e}",
                command="AI",
                e=e,
            )
            return dict(_FALLBACK_RESULT)

        if not isinstance(data, dict):
            return dict(_FALLBACK_RESULT)

        mood = str(data.get("mood", "neutral")).strip() or "neutral"
        tags_raw = data.get("semantic_tags", [])
        if isinstance(tags_raw, list):
            tags = [str(t).strip() for t in tags_raw if t]
        else:
            tags = []
        intent = str(data.get("intent", "")).strip()
        try:
            confidence = float(data.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        return {
            "mood": mood,
            "semantic_tags": tags,
            "intent": intent,
            "confidence": confidence,
        }

    async def analyze_semantics(self, text: str) -> dict:
        """分析用户消息的情感语义

        参数:
            text: 用户消息文本

        返回:
            dict: 含 mood/semantic_tags/intent/confidence 字段
        """
        if not self._is_enabled() or not text or not text.strip():
            return dict(_FALLBACK_RESULT)

        prompt = self._build_prompt(text.strip())
        messages = [{"role": "user", "content": prompt}]

        try:
            response = await llm_helper.chat_text(
                messages,
                options={"temperature": 0.2},
            )
            return self._parse_response(response)
        except Exception as e:
            logger.warning(
                f"贴纸语义分析失败: {e}",
                command="AI",
                e=e,
            )
            return dict(_FALLBACK_RESULT)


sticker_semantics = StickerSemantics()
"""贴纸语义分析器单例"""
