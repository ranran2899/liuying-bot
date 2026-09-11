"""群风格/知识/摘要

LLM驱动的群级抽象：群风格5维度抽取、群知识抽取、
群会话摘要。结果持久化到GroupContextSnapshot。
"""

from datetime import datetime
import json
from typing import Any

from liuying.services.cache import CacheDict
from liuying.utils.log import logger

from ...models.group_context import GroupContextSnapshot
from ..tools.json_utils import extract_json_payload

__all__ = [
    "ProfileToolkit",
    "extract_group_style",
    "group_profile",
]


_STYLE_CACHE_TTL = 3600.0
"""群风格缓存TTL（秒）"""


class ProfileToolkit:
    """群档案工具集

    提供群风格提示词构建等无状态工具方法。
    """

    @staticmethod
    def build_group_style_prompt_block(
        style: dict[str, Any],
    ) -> str:
        """构建群风格prompt注入块

        参数:
            style: 群风格字典

        返回:
            str: prompt文本
        """
        if not style:
            return ""

        tone = style.get("tone", "")
        pace = style.get("pace", "")
        catchphrases = style.get("catchphrases", [])
        taboos = style.get("taboos", [])
        typical = style.get("typical_length", "")

        lines = ["\n\n[群风格参考]"]
        if tone:
            lines.append(f"语气: {tone}")
        if pace:
            lines.append(f"节奏: {pace}")
        if catchphrases:
            phrases = "、".join(str(p) for p in catchphrases[:5])
            lines.append(f"常用语: {phrases}")
        if taboos:
            taboos_str = "、".join(str(t) for t in taboos[:3])
            lines.append(f"避免话题: {taboos_str}")
        if typical:
            lines.append(f"典型句长: {typical}")

        return "\n".join(lines) if len(lines) > 1 else ""


async def extract_group_style(
    group_id: str,
    conversation: str,
    llm_helper: Any,
) -> dict[str, Any]:
    """LLM抽取群风格5维度

    参数:
        group_id: 群组ID
        conversation: 群聊对话文本
        llm_helper: LLM助手

    返回:
        dict: 群风格字典（tone/pace/catchphrases/taboos/typical_length）
    """
    if not conversation.strip():
        return {}

    prompt = (
        "你是群聊风格分析师。下面是一段群聊对话摘要。\n"
        "请总结这个群当前的整体说话风格，包含5个维度：\n"
        "- tone: 语气/氛围（10-20字）\n"
        "- pace: 节奏（慢/中/快+特点）\n"
        "- catchphrases: 口头禅/常用感叹词列表（3-6项）\n"
        "- taboos: 禁忌或敏感话题（0-3项）\n"
        "- typical_length: 典型单句长度（短/中/长+说明）\n\n"
        "只输出严格JSON对象，不要markdown。\n"
        '格式：{"tone":"...","pace":"...","catchphrases":["..."],\n'
        '"taboos":["..."],"typical_length":"..."}\n\n'
        "群聊对话摘要：\n"
        f"{conversation[:2000]}"
    )
    try:
        response = await llm_helper.chat_text(
            [{"role": "user", "content": prompt}],
            options={"temperature": 0.3},
        )
        return extract_json_payload(response) or {}
    except Exception as e:
        logger.warning(
            f"抽取群风格失败 {group_id}: {e}",
            command="AI",
            e=e,
        )
        return {}


class GroupProfileManager:
    """群档案管理器

    管理群风格/知识/摘要的抽取与持久化。
    """

    def __init__(self) -> None:
        """初始化群档案管理器"""
        self._style_cache = CacheDict(
            "AI_GROUP_PROFILE_STYLE", expire=int(_STYLE_CACHE_TTL)
        )
        """群风格缓存：group_id -> style（1小时TTL）"""

    async def get_or_extract_style(
        self,
        group_id: str,
        conversation: str,
        llm_helper: Any,
    ) -> dict[str, Any]:
        """获取或抽取群风格（带缓存）

        参数:
            group_id: 群组ID
            conversation: 群聊对话文本
            llm_helper: LLM助手

        返回:
            dict: 群风格字典
        """
        cached = self._style_cache.get(group_id)
        if cached:
            return cached

        style = await extract_group_style(
            group_id, conversation, llm_helper
        )
        if style:
            self._style_cache.set(group_id, style)
            await self._persist_style(group_id, style)
        return style

    async def _persist_style(
        self,
        group_id: str,
        style: dict[str, Any],
    ) -> None:
        """持久化群风格到GroupContextSnapshot

        参数:
            group_id: 群组ID
            style: 群风格字典
        """
        snapshot = await GroupContextSnapshot.get_or_create(group_id)
        snapshot.style = json.dumps(style, ensure_ascii=False)
        snapshot.last_activity_time = datetime.now()
        await snapshot.save(
            update_fields=["style", "last_activity_time"]
        )


group_profile = GroupProfileManager()
"""群档案管理器单例"""
