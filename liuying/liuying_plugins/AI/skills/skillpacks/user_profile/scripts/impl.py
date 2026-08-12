"""用户画像实现

在长期记忆之上做一层「主动写入 + 画像汇总」，
补齐内置 recall_memory 只读检索的缺口。

用户身份从 Agent 会话上下文取，不作为工具参数暴露给模型，
避免模型伪造他人 user_id 越权读写记忆。
"""

from typing import Any

from liuying.liuying_plugins.AI.agent.runtime.constants import (
    EVIDENCE_KIND_CONTEXT,
    INTENT_TAG_MEMORY,
    LATENCY_CLASS_FAST,
)
from liuying.liuying_plugins.AI.agent.runtime.session_context import (
    get_current_group_id,
    get_current_persona_name,
    get_current_user_id,
)
from liuying.liuying_plugins.AI.agent.tools import AgentTool

_MAX_FACT_LENGTH = 200
"""单条记忆内容上限"""

_PROFILE_LIMIT = 12
"""画像汇总取回的记忆条数"""

_FACT_SALIENCE = 0.8
"""主动记录的事实重要性，高于被动抽取的默认值"""

_FACT_TIER = "long"
"""主动记录的记忆层级，直接进入长期记忆"""


async def remember_fact(
    fact: str,
    tags: list[str] | None = None,
    memory_manager: Any = None,
) -> str:
    """主动记录关于当前用户的事实

    参数:
        fact: 要记住的事实
        tags: 话题标签
        memory_manager: 记忆管理器实例

    返回:
        str: 操作结果描述
    """
    if memory_manager is None:
        return "记忆写入不可用：未配置记忆管理器"
    content = (fact or "").strip()
    if not content:
        return "请提供要记住的内容"
    if len(content) > _MAX_FACT_LENGTH:
        content = content[:_MAX_FACT_LENGTH]

    user_id = get_current_user_id()
    if not user_id:
        return "缺少用户上下文，无法写入记忆"

    memory_id = await memory_manager.add(
        user_id=user_id,
        content=content,
        group_id=get_current_group_id() or None,
        tier=_FACT_TIER,
        topic_tags=[t.strip() for t in (tags or []) if t.strip()]
        or None,
        salience=_FACT_SALIENCE,
        persona_name=get_current_persona_name(),
    )
    return f"已记住（记忆#{memory_id}）：{content}"


async def get_profile(memory_manager: Any = None) -> str:
    """汇总当前用户的画像

    参数:
        memory_manager: 记忆管理器实例

    返回:
        str: 画像文本
    """
    if memory_manager is None:
        return "画像不可用：未配置记忆管理器"

    user_id = get_current_user_id()
    if not user_id:
        return "缺少用户上下文，无法读取画像"

    records = await memory_manager.get_memory_summary(
        user_id=user_id,
        group_id=get_current_group_id() or None,
        limit=_PROFILE_LIMIT,
        persona_name=get_current_persona_name(),
    )
    if not records:
        return "还没有关于这位用户的记忆"

    lines = [f"共{len(records)}条记忆（按时间倒序）："]
    lines.extend(
        f"- [{record.get('tier', '')}] {record.get('summary', '')}"
        f"（{record.get('create_time', '')}）"
        for record in records
    )
    return "\n".join(lines)


def build_profile_tools(runtime: Any) -> list[AgentTool]:
    """构建用户画像工具集

    参数:
        runtime: SkillRuntime 实例

    返回:
        list[AgentTool]: 工具列表
    """
    memory_manager = getattr(runtime, "memory_manager", None)

    async def _remember(
        fact: str, tags: list[str] | None = None
    ) -> str:
        """记忆写入handler

        参数:
            fact: 要记住的事实
            tags: 话题标签

        返回:
            str: 操作结果
        """
        return await remember_fact(
            fact=fact, tags=tags, memory_manager=memory_manager
        )

    async def _profile() -> str:
        """画像汇总handler

        返回:
            str: 画像文本
        """
        return await get_profile(memory_manager=memory_manager)

    return [
        AgentTool(
            name="remember_fact",
            description=(
                "主动记住关于当前用户的重要事实（喜好、身份、约定、"
                "重要日期）。用户明确要求记住、或透露了值得长期保留"
                "的信息时调用；闲聊内容不要调用"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "fact": {
                        "type": "string",
                        "description": (
                            "要记住的事实，写成完整陈述句，"
                            "如「喜欢喝冰美式」"
                        ),
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "话题标签，如 饮食、工作",
                    },
                },
                "required": ["fact"],
            },
            func=_remember,
            intent_tags=[INTENT_TAG_MEMORY],
            latency_class=LATENCY_CLASS_FAST,
            evidence_kind=EVIDENCE_KIND_CONTEXT,
            per_session_quota=3,
        ),
        AgentTool(
            name="get_user_profile",
            description=(
                "查看关于当前用户已记住的全部要点，"
                "适用于「你还记得我什么」类问题"
            ),
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
            func=_profile,
            intent_tags=[INTENT_TAG_MEMORY],
            latency_class=LATENCY_CLASS_FAST,
            evidence_kind=EVIDENCE_KIND_CONTEXT,
        ),
    ]
