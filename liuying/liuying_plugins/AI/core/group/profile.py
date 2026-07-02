"""群风格/知识/摘要

LLM驱动的群级抽象：群风格5维度抽取、群知识抽取、
群会话摘要。结果持久化到GroupContextSnapshot。
"""

from datetime import datetime
import json
import re
from typing import Any

from liuying.services.cache import CacheDict
from liuying.utils.log import logger

from ...agent.runtime.planning.json_utils import extract_json_payload
from ...models.group_context import GroupContextSnapshot

__all__ = [
    "build_group_style_prompt_block",
    "extract_group_knowledge",
    "extract_group_style",
    "group_profile",
    "summarize_conversation",
]


_GROUP_STYLE_PROMPT = """你是群聊风格分析师。下面是一段群聊对话摘要。
请总结这个群当前的整体说话风格，包含5个维度：
- tone: 语气/氛围（10-20字）
- pace: 节奏（慢/中/快+特点）
- catchphrases: 口头禅/常用感叹词列表（3-6项）
- taboos: 禁忌或敏感话题（0-3项）
- typical_length: 典型单句长度（短/中/长+说明）

只输出严格JSON对象，不要markdown。
格式：{"tone":"...","pace":"...","catchphrases":["..."],
"taboos":["..."],"typical_length":"..."}

群聊对话摘要：
{conversation}"""


_GROUP_KNOWLEDGE_PROMPT = """你是群聊知识抽取器。从下面的群聊中抽取群知识。
每条知识包含：
- term: 术语/梗名
- definition: 含义解释
- aliases: 别名列表
- is_meme: 是否为梗（true/false）
- safe_usage: 安全用法说明

只输出JSON数组，不要markdown。
格式：[{{"term":"...","definition":"...","aliases":[],"is_meme":false,"safe_usage":"..."}}]

群聊内容：
{conversation}"""


_SESSION_SUMMARY_PROMPT = """请将以下对话压缩成2-4句中文摘要。
保留人物关系、话题延续、已确认事实和未完成事项。
直接输出摘要，不要列表，不要解释。

对话内容：
{conversation}"""


_STYLE_CACHE_TTL = 3600.0
"""群风格缓存TTL（秒）"""


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

    prompt = _GROUP_STYLE_PROMPT.format(conversation=conversation[:2000])
    try:
        response = await llm_helper.chat_text(
            [{"role": "user", "content": prompt}],
            options={"temperature": 0.3},
        )
        return _parse_json_response(response)
    except Exception as e:
        logger.warning(
            f"抽取群风格失败 {group_id}: {e}",
            command="AI",
            e=e,
        )
        return {}


async def extract_group_knowledge(
    group_id: str,
    conversation: str,
    llm_helper: Any,
) -> list[dict[str, Any]]:
    """LLM抽取群知识

    参数:
        group_id: 群组ID
        conversation: 群聊对话文本
        llm_helper: LLM助手

    返回:
        list[dict]: 知识条目列表
    """
    if not conversation.strip():
        return []

    prompt = _GROUP_KNOWLEDGE_PROMPT.format(
        conversation=conversation[:2000]
    )
    try:
        response = await llm_helper.chat_text(
            [{"role": "user", "content": prompt}],
            options={"temperature": 0.3},
        )
        result = _parse_json_response(response)
        if isinstance(result, list):
            return result
        return []
    except Exception as e:
        logger.warning(
            f"抽取群知识失败 {group_id}: {e}",
            command="AI",
            e=e,
        )
        return []


async def summarize_conversation(
    conversation: str,
    llm_helper: Any,
) -> str:
    """LLM生成会话摘要

    参数:
        conversation: 对话文本
        llm_helper: LLM助手

    返回:
        str: 摘要文本
    """
    if not conversation.strip():
        return ""

    prompt = _SESSION_SUMMARY_PROMPT.format(
        conversation=conversation[:3000]
    )
    try:
        return await llm_helper.chat_text(
            [{"role": "user", "content": prompt}],
            options={"temperature": 0.3},
        )
    except Exception as e:
        logger.warning(
            f"生成会话摘要失败: {e}",
            command="AI",
            e=e,
        )
        return ""


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


def _parse_json_response(response: str) -> Any:
    """解析LLM的JSON响应（委托 extract_json_payload + 数组兜底）

    参数:
        response: LLM响应文本

    返回:
        Any: 解析后的JSON对象（dict或list），失败返回空dict
    """
    result = extract_json_payload(response)
    if result is not None:
        return result
    # 数组兜底：extract_json_payload 只处理 dict，此处补数组解析
    text = (response or "").strip()
    if text.startswith("```"):
        text = "\n".join(
            line for line in text.split("\n")
            if not line.startswith("```")
        )
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, list) else {}
    except (json.JSONDecodeError, ValueError):
        pass
    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        try:
            return json.loads(match.group())
        except (json.JSONDecodeError, ValueError):
            pass
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
        try:
            snapshot = await GroupContextSnapshot.get_or_create(group_id)
            snapshot.style = json.dumps(style, ensure_ascii=False)
            snapshot.last_activity_time = datetime.now()
            await snapshot.save(
                update_fields=["style", "last_activity_time"]
            )
        except Exception as e:
            logger.debug(
                f"持久化群风格失败 {group_id}: {e}",
                command="AI",
                e=e,
            )


group_profile = GroupProfileManager()
"""群档案管理器单例"""
