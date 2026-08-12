"""表情包技能实现

把 core/sticker 的策展与检索能力暴露成 Agent 工具，让模型能在
需要时主动挑表情包，而不只依赖 pipeline 的概率触发。

身份（群号/用户）从 session_context 取，不作为工具参数暴露，
从结构上杜绝模型越权操作他人会话的冷却与偏好数据。
"""

from typing import Any

from liuying.liuying_plugins.AI.agent.runtime.constants import (
    EVIDENCE_KIND_TOOL,
    INTENT_TAG_IMAGE,
    INTENT_TAG_LOCAL,
    LATENCY_CLASS_FAST,
)
from liuying.liuying_plugins.AI.agent.runtime.session_context import (
    get_current_group_id,
    get_current_user_id,
)
from liuying.liuying_plugins.AI.agent.tools import AgentTool
from liuying.liuying_plugins.AI.core.sticker import (
    StickerMood,
    sticker_curation,
    sticker_library,
)

_SEARCH_LIMIT = 5
"""检索结果条数上限，控制送入LLM的token"""

_MOOD_VALUES = [mood.value for mood in StickerMood]
"""全部可选心情标签，用于工具参数的enum约束"""

_TOP_MOODS = 5
"""库统计中展示的心情分布条数"""


def describe_item(item: Any) -> str:
    """把表情包条目格式化为一行描述

    参数:
        item: StickerItem 实例

    返回:
        str: 单行描述
    """
    parts = [item.name or f"#{item.id}"]
    if description := (item.description or "").strip():
        parts.append(description)
    if moods := item.get_mood_tags():
        parts.append("/".join(moods[:3]))
    return " | ".join(parts)


async def select_sticker(
    mood: str = "",
    context: str = "",
) -> str:
    """挑选一个契合当前语境的表情包

    强制模式挑选，跳过概率与冷却检查——模型主动调用即视为
    已判断该发，概率控制交给 pipeline 的自动触发路径。

    参数:
        mood: 期望的心情标签
        context: 当前回复文本或语境描述

    返回:
        str: 选中结果描述，或未选中的原因
    """
    group_id = get_current_group_id() or None
    item = await sticker_curation.choose_for_reply(
        text=(context or "").strip(),
        mood_hint=(mood or "").strip(),
        group_id=group_id,
        user_id=get_current_user_id(),
        is_private=group_id is None,
        force=True,
    )
    if item is None:
        return "表情包库里没有合适的，这次就不发了"

    await sticker_curation.record_usage(
        sticker_id=item.id,
        context_text=(context or "").strip(),
        detected_mood=(mood or "").strip(),
        group_id=group_id or "",
        user_id=get_current_user_id(),
    )
    return (
        f"已选中表情包：{describe_item(item)}"
        f"（文件 {item.file_path}）"
    )


async def search_sticker(query: str, limit: int = _SEARCH_LIMIT) -> str:
    """按关键词检索表情包

    参数:
        query: 查询文本，匹配名称、描述与语义标签
        limit: 返回条数上限

    返回:
        str: 检索结果列表或未命中说明
    """
    query = (query or "").strip()
    if not query:
        return "请提供要查找的表情包关键词"

    capped = max(1, min(int(limit or _SEARCH_LIMIT), _SEARCH_LIMIT))
    items = await sticker_library.search_by_text(query, limit=capped)
    if not items:
        return f"表情包库里没有和「{query}」相关的"

    lines = [
        f"{index}. {describe_item(item)}"
        for index, item in enumerate(items, start=1)
    ]
    return f"找到{len(items)}个相关表情包：\n" + "\n".join(lines)


async def sticker_stats() -> str:
    """汇报表情包库规模与心情分布

    返回:
        str: 统计描述
    """
    stats = await sticker_library.get_stats()
    if not stats.total:
        return "表情包库还是空的，一个都没有"

    top = sorted(
        stats.by_mood.items(), key=lambda kv: kv[1], reverse=True
    )[:_TOP_MOODS]
    mood_text = "、".join(f"{mood}{count}个" for mood, count in top)
    lines = [
        f"表情包库共{stats.total}个，"
        f"可用{stats.active}个，禁用{stats.disabled}个。"
    ]
    if mood_text:
        lines.append(f"心情分布：{mood_text}。")
    if stats.total_usage:
        lines.append(f"累计使用{stats.total_usage}次。")
    return "".join(lines)


def build_sticker_tools(runtime: Any) -> list[AgentTool]:
    """构建表情包工具集

    参数:
        runtime: SkillRuntime 实例

    返回:
        list[AgentTool]: 工具列表
    """
    del runtime  # 表情包服务为全局单例，无需从 runtime 注入

    return [
        AgentTool(
            name="select_sticker",
            description=(
                "挑一个契合当前情绪的表情包发出去。想用表情包"
                "表达情绪、或用户明确要求发表情包时用本工具。"
                "只在确实想发时才调用，不要每句话都配表情"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "mood": {
                        "type": "string",
                        "enum": _MOOD_VALUES,
                        "description": "期望的心情标签",
                    },
                    "context": {
                        "type": "string",
                        "description": (
                            "即将发出的回复文本或当前语境，"
                            "用于辅助匹配"
                        ),
                    },
                },
                "required": [],
            },
            func=select_sticker,
            intent_tags=[INTENT_TAG_IMAGE, INTENT_TAG_LOCAL],
            latency_class=LATENCY_CLASS_FAST,
            evidence_kind=EVIDENCE_KIND_TOOL,
            per_session_quota=2,
        ),
        AgentTool(
            name="search_sticker",
            description=(
                "按关键词查表情包库里有什么。用户问「你有没有"
                "XX的表情包」时用本工具查证后再回答，"
                "不要凭空说有或没有"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "关键词，匹配表情包名称、描述与语义标签"
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": (
                            f"返回条数，1-{_SEARCH_LIMIT}，默认{_SEARCH_LIMIT}"
                        ),
                    },
                },
                "required": ["query"],
            },
            func=search_sticker,
            intent_tags=[INTENT_TAG_IMAGE, INTENT_TAG_LOCAL],
            latency_class=LATENCY_CLASS_FAST,
            evidence_kind=EVIDENCE_KIND_TOOL,
        ),
        AgentTool(
            name="sticker_stats",
            description=(
                "查表情包库的规模与心情分布。用户问「你有多少"
                "表情包」这类量级问题时用本工具"
            ),
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
            func=sticker_stats,
            intent_tags=[INTENT_TAG_IMAGE, INTENT_TAG_LOCAL],
            latency_class=LATENCY_CLASS_FAST,
            evidence_kind=EVIDENCE_KIND_TOOL,
        ),
    ]
