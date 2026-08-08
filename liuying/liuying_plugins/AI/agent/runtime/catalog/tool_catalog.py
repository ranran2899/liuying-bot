"""工具目录分类

将工具按用途分类，供规划器和工具选择器使用。
支持基于意图标签的语义化工具推荐。
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from ..constants import (
    INTENT_TAG_ADMIN,
    INTENT_TAG_IMAGE,
    INTENT_TAG_LOCAL,
    INTENT_TAG_MEMORY,
    INTENT_TAG_NETWORK,
    INTENT_TAG_PLUGIN,
    INTENT_TAG_REALTIME,
)


@dataclass(slots=True)
class ToolCategory:
    """工具分类项

    Attributes:
        name: 分类名
        description: 分类描述
        tool_names: 该分类下的工具名列表
        intent_tag: 关联的意图标签
        priority: 优先级（数字越小优先级越高）
    """

    name: str
    description: str
    tool_names: list[str] = field(default_factory=list)
    intent_tag: str = ""
    priority: int = 100


class ToolCatalog:
    """工具目录管理器

    将注册表中的工具按用途分类，支持：
    1. 基于意图标签推荐工具
    2. 按延迟级别排序
    3. 按是否需要网络/图片分组
    """

    def __init__(self) -> None:
        """初始化工具目录"""
        self._categories: dict[str, ToolCategory] = {}
        self._tool_to_category: dict[str, str] = {}
        self._init_default_categories()

    def _init_default_categories(self) -> None:
        """初始化默认分类"""
        defaults = [
            ToolCategory(
                name="image_required",
                description="需要图片输入的工具",
                intent_tag=INTENT_TAG_IMAGE,
                priority=10,
            ),
            ToolCategory(
                name="image_generation",
                description="图片生成工具",
                intent_tag=INTENT_TAG_IMAGE,
                priority=20,
            ),
            ToolCategory(
                name="lightweight_lookup",
                description="轻量查证工具（本地快速）",
                intent_tag=INTENT_TAG_LOCAL,
                priority=30,
            ),
            ToolCategory(
                name="plugin_local",
                description="插件本地能力",
                intent_tag=INTENT_TAG_PLUGIN,
                priority=40,
            ),
            ToolCategory(
                name="plugin_network",
                description="插件网络能力",
                intent_tag=INTENT_TAG_NETWORK,
                priority=50,
            ),
            ToolCategory(
                name="network_search",
                description="网络搜索工具",
                intent_tag=INTENT_TAG_REALTIME,
                priority=60,
            ),
            ToolCategory(
                name="memory_recall",
                description="记忆召回工具",
                intent_tag=INTENT_TAG_MEMORY,
                priority=70,
            ),
            ToolCategory(
                name="admin_ops",
                description="管理操作工具",
                intent_tag=INTENT_TAG_ADMIN,
                priority=80,
            ),
        ]
        for cat in defaults:
            self._categories[cat.name] = cat

    def register_tool(
        self,
        tool_name: str,
        category: str,
        intent_tags: list[str] | None = None,
    ) -> None:
        """注册工具到分类

        参数:
            tool_name: 工具名
            category: 分类名
            intent_tags: 意图标签列表（可选）
        """
        if category not in self._categories:
            self._categories[category] = ToolCategory(
                name=category,
                description=f"自定义分类: {category}",
                priority=100,
            )
        if tool_name not in self._categories[category].tool_names:
            self._categories[category].tool_names.append(tool_name)
        self._tool_to_category[tool_name] = category

    def unregister_tool(self, tool_name: str) -> None:
        """从分类中移除工具

        参数:
            tool_name: 工具名
        """
        category_name = self._tool_to_category.pop(tool_name, "")
        if category_name and category_name in self._categories:
            cat = self._categories[category_name]
            if tool_name in cat.tool_names:
                cat.tool_names.remove(tool_name)

    def get_category(self, tool_name: str) -> str:
        """获取工具所属分类

        参数:
            tool_name: 工具名

        返回:
            str: 分类名（未分类返回空串）
        """
        return self._tool_to_category.get(tool_name, "")

    def get_tools_by_category(self, category: str) -> list[str]:
        """获取分类下所有工具

        参数:
            category: 分类名

        返回:
            list[str]: 工具名列表
        """
        cat = self._categories.get(category)
        return list(cat.tool_names) if cat else []

    def recommend_tools(
        self,
        intent_tags: list[str],
        exclude: set[str] | None = None,
    ) -> list[str]:
        """基于意图标签推荐工具

        参数:
            intent_tags: 意图标签列表
            exclude: 需排除的工具名集合

        返回:
            list[str]: 推荐的工具名列表（按优先级排序）
        """
        exclude_set = exclude or set()
        scores: dict[str, int] = defaultdict(int)
        for cat in self._categories.values():
            if cat.intent_tag and cat.intent_tag in intent_tags:
                for tool_name in cat.tool_names:
                    if tool_name not in exclude_set:
                        scores[tool_name] += 100 - cat.priority
        return sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

    def categorize_by_metadata(
        self, tool_name: str, metadata: dict[str, Any]
    ) -> str:
        """根据工具元数据自动分类

        参数:
            tool_name: 工具名
            metadata: 工具元数据

        返回:
            str: 分类名
        """
        requires_image = metadata.get("requires_image", False)
        requires_network = metadata.get("requires_network", False)
        intent_tags = metadata.get("intent_tags", [])
        latency_class = metadata.get("latency_class", "fast")

        if requires_image and "generate" in tool_name.lower():
            category = "image_generation"
        elif requires_image:
            category = "image_required"
        elif requires_network and INTENT_TAG_REALTIME in intent_tags:
            category = "network_search"
        elif requires_network:
            category = "plugin_network"
        elif INTENT_TAG_MEMORY in intent_tags:
            category = "memory_recall"
        elif INTENT_TAG_ADMIN in intent_tags:
            category = "admin_ops"
        elif INTENT_TAG_PLUGIN in intent_tags:
            category = "plugin_local"
        elif latency_class == "fast":
            category = "lightweight_lookup"
        else:
            category = "plugin_local"

        self.register_tool(tool_name, category, intent_tags)
        return category

    def list_categories(self) -> list[ToolCategory]:
        """列出所有分类

        返回:
            list[ToolCategory]: 分类列表（按优先级排序）
        """
        return sorted(
            self._categories.values(), key=lambda x: x.priority
        )

    def build_catalog_prompt(self, registry=None) -> str:
        """构建工具目录提示文本（供规划器使用）

        当传入 registry 时，展示每个工具的描述与必填参数，
        供 LLM 正确生成 tool_args，避免漏传必填项。

        参数:
            registry: 工具注册表，传入时展示工具详情

        返回:
            str: 目录提示文本
        """
        lines = ["可用工具分类:"]
        for cat in self.list_categories():
            if not cat.tool_names:
                continue
            lines.append(f"- [{cat.name}] {cat.description}:")
            for tool_name in cat.tool_names:
                if registry is None:
                    lines.append(f"  - {tool_name}")
                    continue
                tool = registry.get(tool_name)
                if tool is None or tool.is_disabled:
                    continue
                desc = tool.description or ""
                schema = tool.parameters or {}
                required = schema.get("required", []) or []
                props = schema.get("properties", {}) or {}
                if required:
                    params = []
                    for r in required:
                        pdesc = props.get(r, {}).get(
                            "description", ""
                        )
                        params.append(
                            f"{r}({pdesc})" if pdesc else r
                        )
                    req_str = f" | 必填: {', '.join(params)}"
                else:
                    req_str = " | 无必填参数"
                lines.append(f"  - {tool_name}: {desc}{req_str}")
        return "\n".join(lines)


# 轻量查证工具：闲聊场景也放行，让模型"想查就能查"
_LIGHTWEIGHT_LOOKUP_TOOL_NAMES: set[str] = {
    "web_search",
    "fetch_webpage",
    "recall_memory",
    "get_favor",
    "get_datetime",
    "search_plugin_knowledge",
}
"""闲聊场景放行的轻量查证工具名白名单"""

# 管理类工具，非管理场景一律过滤
_ADMIN_TOOL_NAMES: set[str] = set()
"""管理工具名集合（动态填充）"""


def _tool_intent_tags(tool) -> set[str]:
    """获取工具的意图标签集合"""
    return {str(t).strip() for t in (tool.intent_tags or []) if str(t).strip()}


def _is_admin_tool(tool) -> bool:
    """判断是否为管理类工具"""
    tags = _tool_intent_tags(tool)
    return INTENT_TAG_ADMIN in tags


def select_tool_schemas(
    registry,
    *,
    has_images: bool,
    intent_tags: list[str] | None = None,
) -> list[dict[str, Any]]:
    """按意图过滤可见工具schema

    参考参考插件 tool_catalog.select_tool_schemas 设计：
    按当前意图标签和是否有图片，过滤暴露给模型的工具schema，
    减少每次模型调用的schema token开销。

    过滤规则：
    - 管理类工具非管理场景一律过滤
    - 纯闲聊（无realtime/network/plugin/image）：只放行轻量查证工具
    - 有image标签：放行图片相关工具
    - 有realtime/network标签：放行网络工具
    - 有plugin标签：放行插件工具
    - 有memory标签：放行记忆工具

    参数:
        registry: 工具注册表
        has_images: 是否有图片输入
        intent_tags: 意图标签列表

    返回:
        list[dict]: 过滤后的OpenAI schema列表
    """
    schemas = registry.to_openai_schemas()
    if not schemas:
        return []

    tags = {str(t).strip() for t in (intent_tags or []) if str(t).strip()}
    is_chat_only = not tags or not (
        tags & {
            INTENT_TAG_REALTIME,
            INTENT_TAG_NETWORK,
            INTENT_TAG_PLUGIN,
            INTENT_TAG_IMAGE,
            INTENT_TAG_ADMIN,
        }
    )

    result: list[dict[str, Any]] = []
    for schema in schemas:
        func = schema.get("function", {}) if isinstance(schema, dict) else {}
        name = str(func.get("name", "") or "").strip()
        tool = registry.get(name)
        if tool is None or tool.is_disabled:
            continue
        # 管理工具非管理场景过滤
        if _is_admin_tool(tool) and INTENT_TAG_ADMIN not in tags:
            continue
        tool_tags = _tool_intent_tags(tool)

        # 纯闲聊：只放行轻量查证工具
        if is_chat_only:
            if name in _LIGHTWEIGHT_LOOKUP_TOOL_NAMES:
                result.append(schema)
            elif has_images and tool.requires_image:
                result.append(schema)
            continue

        # 有意图标签：按标签放行
        should_include = False
        if INTENT_TAG_IMAGE in tags and (
            tool.requires_image or INTENT_TAG_IMAGE in tool_tags
        ):
            should_include = True
        if (INTENT_TAG_REALTIME in tags or INTENT_TAG_NETWORK in tags) and (
            tool.requires_network
            or INTENT_TAG_REALTIME in tool_tags
            or INTENT_TAG_NETWORK in tool_tags
        ):
            should_include = True
        if INTENT_TAG_PLUGIN in tags and INTENT_TAG_PLUGIN in tool_tags:
            should_include = True
        if INTENT_TAG_MEMORY in tags and INTENT_TAG_MEMORY in tool_tags:
            should_include = True
        if INTENT_TAG_LOCAL in tags and INTENT_TAG_LOCAL in tool_tags:
            should_include = True
        # 轻量查证工具始终放行（想查就能查）
        if name in _LIGHTWEIGHT_LOOKUP_TOOL_NAMES:
            should_include = True
        if should_include:
            result.append(schema)
    return result


def semantic_tool_guidance() -> str:
    """工具使用总原则指导文本

    参考参考插件 semantic_tool_guidance 设计，返回自然语言指导，
    注入到system消息，指导模型正确使用工具。

    返回:
        str: 工具使用指导文本
    """
    return (
        "工具使用总原则：能直接回答就别起工具；不确定、高风险、时效性强、"
        "明显需要查证时再调用工具。"
        "当当前消息包含你不认识、无法确定指代或可能有圈内含义的专有名词、"
        "角色名、作品名、游戏/动漫术语、外号、别称、缩写、谐音、梗或活动名时，"
        "如果可用工具里有联网搜索，必须先调用查证；不要凭记忆猜，"
        "也不要直接在群里问这是什么梗/什么意思。"
        "用户明确要求生成图片时，必须调用图片生成工具，不要只给提示词。"
        "最终回复只输出纯文本，不要markdown、项目符号列表、编号列表，"
        "也不要说正在查询、根据搜索结果或我需要确认一下。"
        "群聊接梗场景优先像群友接话，不要为了显得聪明而滥用工具。"
    )


# 工具默认元数据表：按工具名补全 intent_tags/evidence_kind/latency_class 等。
# 参考参考插件 tool_catalog._default_tool_metadata 设计，
# 技能包显式声明的元数据会覆盖默认值。
_TOOL_METADATA_DEFAULTS: dict[str, dict[str, Any]] = {
    # 网络搜索类
    "web_search": {
        "intent_tags": [INTENT_TAG_REALTIME, INTENT_TAG_NETWORK],
        "evidence_kind": "web",
        "requires_network": True,
        "latency_class": "network",
    },
    "fetch_webpage": {
        "intent_tags": [INTENT_TAG_NETWORK],
        "evidence_kind": "web",
        "requires_network": True,
        "latency_class": "network",
    },
    # 插件知识类
    "search_plugin_knowledge": {
        "intent_tags": [INTENT_TAG_PLUGIN, INTENT_TAG_LOCAL],
        "evidence_kind": "plugin",
        "latency_class": "fast",
    },
    "get_plugin_detail": {
        "intent_tags": [INTENT_TAG_PLUGIN, INTENT_TAG_LOCAL],
        "evidence_kind": "plugin",
        "latency_class": "fast",
    },
    "list_available_plugins": {
        "intent_tags": [INTENT_TAG_PLUGIN, INTENT_TAG_LOCAL],
        "evidence_kind": "plugin",
        "latency_class": "fast",
    },
    # 记忆类
    "recall_memory": {
        "intent_tags": [INTENT_TAG_MEMORY],
        "evidence_kind": "memory",
        "latency_class": "fast",
    },
    # 插件调用类
    "invoke_plugin_command": {
        "intent_tags": [INTENT_TAG_PLUGIN, INTENT_TAG_LOCAL],
        "evidence_kind": "plugin",
        "latency_class": "slow",
    },
    "get_plugin_command_help": {
        "intent_tags": [INTENT_TAG_PLUGIN, INTENT_TAG_LOCAL],
        "evidence_kind": "plugin",
        "latency_class": "fast",
    },
    "search_plugin_by_capability": {
        "intent_tags": [INTENT_TAG_PLUGIN, INTENT_TAG_LOCAL],
        "evidence_kind": "plugin",
        "latency_class": "fast",
    },
    # 图片生成类
    "image_generate": {
        "intent_tags": [INTENT_TAG_IMAGE],
        "evidence_kind": "media",
        "latency_class": "slow",
        "requires_network": True,
    },
    # 内置技能包
    "get_news": {
        "intent_tags": [INTENT_TAG_REALTIME, INTENT_TAG_NETWORK],
        "evidence_kind": "web",
        "requires_network": True,
        "latency_class": "network",
    },
    "get_weather": {
        "intent_tags": [INTENT_TAG_REALTIME, INTENT_TAG_NETWORK],
        "evidence_kind": "web",
        "requires_network": True,
        "latency_class": "network",
    },
    "get_current_time": {
        "intent_tags": [INTENT_TAG_LOCAL],
        "evidence_kind": "context",
        "latency_class": "fast",
    },
    "search_wiki": {
        "intent_tags": [INTENT_TAG_NETWORK],
        "evidence_kind": "web",
        "requires_network": True,
        "latency_class": "network",
    },
    "get_game_info": {
        "intent_tags": [INTENT_TAG_NETWORK],
        "evidence_kind": "web",
        "requires_network": True,
        "latency_class": "network",
    },
    # 群组查询类
    "get_group_members": {
        "intent_tags": [INTENT_TAG_LOCAL],
        "evidence_kind": "context",
        "latency_class": "fast",
    },
    "get_group_member_info": {
        "intent_tags": [INTENT_TAG_LOCAL],
        "evidence_kind": "context",
        "latency_class": "fast",
    },
    "find_group_member": {
        "intent_tags": [INTENT_TAG_LOCAL],
        "evidence_kind": "context",
        "latency_class": "fast",
    },
    # 上下文查询类
    "get_favor": {
        "intent_tags": [INTENT_TAG_LOCAL],
        "evidence_kind": "context",
        "latency_class": "fast",
    },
    "get_datetime": {
        "intent_tags": [INTENT_TAG_LOCAL],
        "evidence_kind": "context",
        "latency_class": "fast",
    },
}
"""工具默认元数据表"""


def apply_tool_metadata_defaults(registry) -> None:
    """为注册表中所有工具补全默认元数据

    参考参考插件 tool_catalog.apply_tool_metadata_defaults 设计：
    按 _TOOL_METADATA_DEFAULTS 表补全缺失的元数据字段，
    工具显式声明的值优先于默认值。

    参数:
        registry: ToolRegistry 实例
    """
    for tool in registry.active_tools():
        defaults = _TOOL_METADATA_DEFAULTS.get(tool.name, {})
        if not defaults:
            continue
        # intent_tags: 默认值仅在工具未声明时填充
        if not tool.intent_tags:
            tool.intent_tags = list(defaults.get("intent_tags", []))
        # evidence_kind: 默认值仅在工具仍为默认值时填充
        if tool.evidence_kind == "tool":
            tool.evidence_kind = defaults.get("evidence_kind", "tool")
        # latency_class: 默认值仅在工具仍为默认值时填充
        if tool.latency_class == "fast":
            tool.latency_class = defaults.get("latency_class", "fast")
        # requires_network: 默认值仅在工具为 False 时填充
        if not tool.requires_network:
            tool.requires_network = defaults.get(
                "requires_network", False
            )
        # requires_image: 默认值仅在工具为 False 时填充
        if not tool.requires_image:
            tool.requires_image = defaults.get("requires_image", False)
        # 重新分类以反映更新后的元数据
        # categorize_by_metadata 内部已调用 register_tool，无需重复注册
        tool_catalog.categorize_by_metadata(
            tool.name, tool.to_metadata()
        )


# 全局单例
tool_catalog = ToolCatalog()
"""工具目录单例"""
