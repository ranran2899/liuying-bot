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

    def build_catalog_prompt(self) -> str:
        """构建工具目录提示文本（供规划器使用）

        返回:
            str: 目录提示文本
        """
        lines = ["可用工具分类:"]
        for cat in self.list_categories():
            if not cat.tool_names:
                continue
            tools_str = ", ".join(cat.tool_names)
            lines.append(
                f"- [{cat.name}] {cat.description}: {tools_str}"
            )
        return "\n".join(lines)


# 全局单例
tool_catalog = ToolCatalog()
"""工具目录单例"""
