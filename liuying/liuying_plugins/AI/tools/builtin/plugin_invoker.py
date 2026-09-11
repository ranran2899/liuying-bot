"""插件调用器内置工具

代理查询并构造其他已加载插件的命令文本。
通过知识库检索插件命令格式，再由 LLM 将用户意图
转写为符合目标插件语法的命令字符串，供 Agent 在回复中
建议用户执行或由上层流水线代为发送。
"""

from typing import Any

from liuying.utils.log import logger

from ...agent.runtime.constants import (
    EVIDENCE_KIND_CONTEXT,
    INTENT_TAG_LOCAL,
    INTENT_TAG_PLUGIN,
    LATENCY_CLASS_FAST,
)
from ...core.knowledge import knowledge_store
from ...core.llm import llm_helper
from ...core.llm.model_router import ROLE_AGENT, model_router
from ..decorators import register_tool

_MAX_COMMANDS_IN_PROMPT = 8
"""提示词中最多携带的命令数量"""


def _format_commands_for_prompt(
    commands: list[dict[str, Any]],
) -> str:
    """格式化命令列表为提示词文本

    参数:
        commands: 命令字典列表

    返回:
        str: 格式化后的文本
    """
    if not commands:
        return "（无命令信息）"
    lines: list[str] = []
    for cmd in commands[:_MAX_COMMANDS_IN_PROMPT]:
        name = str(cmd.get("command") or "")
        params = " ".join(f"[{p}]" for p in cmd.get("params") or [])
        desc = str(cmd.get("description") or "")
        lines.append(f"- {name} {params}: {desc}")
    return "\n".join(lines)


async def _resolve_plugin_commands(
    plugin_name: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """解析插件命令格式

    先按名称/模块名精确匹配；失败则用语义召回兜底，
    取最相关插件再查，避免 LLM 传入显示名或中文
    关键词（如「商店」）时查不到命令清单。

    参数:
        plugin_name: 插件模块名或用户描述

    返回:
        tuple: (插件完整信息, 命令列表)
    """
    if not plugin_name:
        return None, []
    try:
        info = await knowledge_store.get_by_name(plugin_name)
    except Exception as e:
        logger.debug(
            f"查询插件失败: {plugin_name} -> {e}",
            command="AI",
            e=e,
        )
        info = None
    if info is None:
        try:
            results = await knowledge_store.recall(
                plugin_name, top_k=1, log_query=False
            )
        except Exception as e:
            logger.debug(
                f"召回插件失败: {plugin_name} -> {e}",
                command="AI",
                e=e,
            )
            results = []
        info = results[0].info if results else None
    if info is None:
        return None, []
    commands = list(info.get("commands") or [])
    return info, commands


@register_tool(
    name="invoke_plugin_command",
    description=(
        "代理调用流萤机器人其他已加载插件的功能。"
        "根据用户意图和目标插件名，自动构造可直接执行的命令文本。"
        "适用于用户希望通过AI代为触发签到/抽签/天气等插件功能时"
    ),
    parameters={
        "type": "object",
        "properties": {
            "plugin_name": {
                "type": "string",
                "description": (
                    "目标插件模块名或显示名关键词"
                    "（如 shop/wife/fortune/商店/签到）"
                ),
            },
            "user_intent": {
                "type": "string",
                "description": "用户想做的事情（自然语言）",
            },
        },
        "required": ["plugin_name", "user_intent"],
    },
    intent_tags=[INTENT_TAG_PLUGIN, INTENT_TAG_LOCAL],
    latency_class=LATENCY_CLASS_FAST,
    evidence_kind=EVIDENCE_KIND_CONTEXT,
    metadata={"knowledge_source": "plugin_meta"},
)
async def invoke_plugin_command(
    plugin_name: str, user_intent: str
) -> str:
    """代理调用其他插件命令

    参数:
        plugin_name: 目标插件模块名
        user_intent: 用户自然语言意图

    返回:
        str: 构造好的命令文本，或失败原因说明
    """
    brief, commands = await _resolve_plugin_commands(plugin_name)
    if brief is None:
        return f"未找到插件: {plugin_name}"
    display_name = str(brief.get("name") or plugin_name)
    if not commands:
        return f"插件 {display_name} 未暴露任何命令格式"
    try:
        prompt = (
            "你是一个命令转写助手。\n"
            "请根据目标插件的命令格式说明，将用户的自然语言意图转写为一条可直接执行的命令文本。\n"
            "\n"
            f"目标插件：{plugin_name}\n"
            f"插件说明：{brief.get('description', '')}\n"
            "命令格式列表（JSON）：\n"
            f"{_format_commands_for_prompt(commands)}\n"
            "\n"
            f"用户意图：{user_intent}\n"
            "\n"
            "要求：\n"
            "1. 只输出一条命令文本，不要任何解释或多行\n"
            "2. 严格遵循命令格式中的前缀和参数顺序\n"
            "3. 参数缺失时使用合理的默认值或占位符\n"
            "4. 若用户意图与插件能力无关，输出空字符串"
        )
        role = model_router.resolve(ROLE_AGENT)
        command_text = await llm_helper.chat_text(
            [{"role": "user", "content": prompt}],
            model=role.model or None,
            options=role.apply_to_options({"temperature": 0.2}),
            provider_name=role.provider or None,
        )
        command_text = command_text.strip()
        if not command_text:
            return (
                f"无法将意图转写为 {display_name} "
                "的命令，请用户手动使用该插件"
            )
        # 安全校验：仅接受以插件注册命令开头的单行命令，
        # 防止 LLM 输出越权内容被上层流水线代发
        first_line = command_text.splitlines()[0].strip()
        allowed = tuple(
            str(c.get("command") or "")
            for c in commands
            if c.get("command")
        )
        if not allowed or not first_line.startswith(allowed):
            return (
                f"生成的命令与插件 {display_name} "
                "的注册命令不匹配，已拒绝执行"
            )
        return (
            f"已构造命令: {first_line}\n"
            f"来源插件: {display_name}"
        )
    except Exception as e:
        logger.warning(
            f"插件命令转写失败: {plugin_name} -> {e}",
            command="AI",
            e=e,
        )
        return f"命令转写失败: {type(e).__name__}"


@register_tool(
    name="get_plugin_command_help",
    description=(
        "查询指定插件的命令用法清单，"
        "适用于用户询问某插件如何使用、需要命令格式参考时"
    ),
    parameters={
        "type": "object",
        "properties": {
            "plugin_name": {
                "type": "string",
                "description": (
                    "插件模块名或显示名关键词"
                    "（如 shop/wife/fortune/商店/签到）"
                ),
            },
        },
        "required": ["plugin_name"],
    },
    intent_tags=[INTENT_TAG_PLUGIN, INTENT_TAG_LOCAL],
    latency_class=LATENCY_CLASS_FAST,
    evidence_kind=EVIDENCE_KIND_CONTEXT,
    metadata={"knowledge_source": "plugin_meta"},
)
async def get_plugin_command_help(plugin_name: str) -> str:
    """查询插件命令用法清单

    参数:
        plugin_name: 插件模块名

    返回:
        str: 命令用法文本
    """
    brief, commands = await _resolve_plugin_commands(plugin_name)
    if brief is None:
        return f"未找到插件: {plugin_name}"
    if not commands:
        return f"插件 {brief.get('name') or plugin_name} 暂无命令说明"
    header = f"插件 {brief.get('name') or plugin_name} 命令清单:"
    return f"{header}\n{_format_commands_for_prompt(commands)}"


@register_tool(
    name="search_plugin_by_capability",
    description=(
        "按功能关键词搜索可用插件，"
        "适用于用户描述需求但不确定用哪个插件时"
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "功能描述或关键词",
            },
            "top_k": {
                "type": "integer",
                "description": "返回数量，默认3，最大5",
                "default": 3,
            },
        },
        "required": ["query"],
    },
    intent_tags=[INTENT_TAG_PLUGIN, INTENT_TAG_LOCAL],
    latency_class=LATENCY_CLASS_FAST,
    evidence_kind=EVIDENCE_KIND_CONTEXT,
    metadata={"knowledge_source": "plugin_meta"},
)
async def search_plugin_by_capability(
    query: str, top_k: int = 3
) -> str:
    """按功能搜索插件

    参数:
        query: 功能描述或关键词
        top_k: 返回数量

    返回:
        str: 插件推荐文本
    """
    try:
        results = await knowledge_store.recall(
            query,
            top_k=min(max(top_k, 1), 5),
            log_query=False,
        )
        if not results:
            return f"未找到与「{query}」相关的插件"
        lines: list[str] = [
            f"与「{query}」相关的插件推荐:"
        ]
        for r in results:
            brief = r.to_brief()
            name = brief.get("display_name") or brief.get(
                "plugin_name", ""
            )
            desc = brief.get("description", "")
            commands = brief.get("commands", [])
            cmd_names = ",".join(
                c.get("command", "") for c in commands[:3]
            )
            lines.append(
                f"- {name}（{brief.get('plugin_name')}）"
                f": {desc} | 命令: {cmd_names}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"搜索失败: {type(e).__name__}"


__all__ = [
    "get_plugin_command_help",
    "invoke_plugin_command",
    "search_plugin_by_capability",
]
