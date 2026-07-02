"""知识库类内置工具

插件知识检索 + 插件详情查询 + 插件列表。
"""

from ....core.knowledge import knowledge_store
from ...runtime.constants import (
    EVIDENCE_KIND_CONTEXT,
    INTENT_TAG_LOCAL,
    INTENT_TAG_PLUGIN,
    LATENCY_CLASS_FAST,
)
from ..decorators import register_tool


@register_tool(
    name="search_plugin_knowledge",
    description=(
        "检索流萤机器人已加载插件的命令与功能说明，"
        "适用于用户询问某功能是否存在、如何使用某插件、"
        "或需要推荐合适插件时"
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "查询文本（用户问题或关键词）",
            },
            "top_k": {
                "type": "integer",
                "description": "返回数量，默认5，最大10",
                "default": 5,
            },
        },
        "required": ["query"],
    },
    intent_tags=[INTENT_TAG_PLUGIN, INTENT_TAG_LOCAL],
    latency_class=LATENCY_CLASS_FAST,
    evidence_kind=EVIDENCE_KIND_CONTEXT,
    metadata={"knowledge_source": "plugin_meta"},
)
async def search_plugin_knowledge(
    query: str, top_k: int = 5
) -> str:
    """检索插件知识库

    参数:
        query: 查询文本（用户问题或关键词）
        top_k: 返回数量，默认5

    返回:
        str: 检索结果文本
    """
    try:
        results = await knowledge_store.recall(
            query,
            top_k=min(max(top_k, 1), 10),
            log_query=False,
        )
        if not results:
            return "未找到相关插件"
        lines: list[str] = []
        for r in results:
            brief = r.to_brief()
            name = brief.get("display_name") or brief.get(
                "plugin_name", ""
            )
            desc = brief.get("description", "")
            score = brief.get("score", 0.0)
            lines.append(
                f"- {name}（{brief.get('plugin_name')}）"
                f" [score={score}]: {desc}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"知识库检索失败: {e}"


@register_tool(
    name="get_plugin_detail",
    description=(
        "按插件模块名查询完整详情（含命令/参数/AI工具/用法），"
        "适用于需要给用户提供具体命令格式或深度介绍时"
    ),
    parameters={
        "type": "object",
        "properties": {
            "plugin_name": {
                "type": "string",
                "description": "插件模块名（如 wife/fortune）",
            },
        },
        "required": ["plugin_name"],
    },
    intent_tags=[INTENT_TAG_PLUGIN, INTENT_TAG_LOCAL],
    latency_class=LATENCY_CLASS_FAST,
    evidence_kind=EVIDENCE_KIND_CONTEXT,
    metadata={"knowledge_source": "plugin_meta"},
)
async def get_plugin_detail(plugin_name: str) -> str:
    """查询插件详情

    参数:
        plugin_name: 插件模块名

    返回:
        str: 插件详情文本
    """
    try:
        item = await knowledge_store.get_by_name(plugin_name)
        if not item:
            return f"未找到插件: {plugin_name}"
        return item.build_prompt_block()
    except Exception as e:
        return f"查询插件详情失败: {e}"


@register_tool(
    name="list_available_plugins",
    description=(
        "列出所有可用插件（按菜单类型分组），"
        "适用于用户询问机器人有哪些功能、查看插件目录时"
    ),
    parameters={
        "type": "object",
        "properties": {
            "menu_type": {
                "type": "string",
                "description": (
                    "菜单类型过滤（如 功能/娱乐/管理/AI），"
                    "空串表示全部"
                ),
                "default": "",
            },
        },
        "required": [],
    },
    intent_tags=[INTENT_TAG_PLUGIN, INTENT_TAG_LOCAL],
    latency_class=LATENCY_CLASS_FAST,
    evidence_kind=EVIDENCE_KIND_CONTEXT,
    metadata={"knowledge_source": "plugin_meta"},
)
async def list_available_plugins(menu_type: str = "") -> str:
    """列出可用插件

    参数:
        menu_type: 菜单类型过滤，空串表示全部

    返回:
        str: 插件列表文本
    """
    try:
        items = await knowledge_store.list_enabled(
            menu_type=menu_type or None, limit=100
        )
        if not items:
            return "暂无可用插件"
        lines: list[str] = []
        current_menu = ""
        for item in items:
            if item.menu_type != current_menu:
                current_menu = item.menu_type or "其他"
                lines.append(f"\n[{current_menu}]")
            name = item.display_name or item.plugin_name
            desc = item.description[:60] if item.description else ""
            lines.append(f"- {name}（{item.plugin_name}）: {desc}")
        return "\n".join(lines)
    except Exception as e:
        return f"列出插件失败: {e}"
