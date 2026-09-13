"""工具目录分类

将工具按用途分类，供规划器和工具选择器使用。
支持基于意图标签的语义化工具推荐。
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .constants import (
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
