"""知识库数据类型

定义召回结果与知识库统计的数据结构。
RecallResult 通过 TYPE_CHECKING 引用 PluginView 以规避循环依赖。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .store import PluginView


@dataclass(slots=True)
class RecallResult:
    """召回结果

    属性:
        plugin: 插件视图
        score: 匹配评分
        matched_fields: 命中字段列表
    """

    plugin: "PluginView"
    score: float = 0.0
    matched_fields: list[str] = field(default_factory=list)

    def to_brief(self) -> dict[str, Any]:
        """导出简要信息

        返回:
            dict: 简要信息字典（含评分）
        """
        brief = self.plugin.to_brief()
        brief["score"] = round(self.score, 3)
        brief["matched_fields"] = list(self.matched_fields)
        return brief


@dataclass(slots=True)
class KnowledgeStats:
    """知识库统计

    属性:
        total: 总插件数
        enabled: 启用插件数
        with_smart_tools: 含AI工具的插件数
        total_commands: 总命令数
        total_tools: 总AI工具数
        hot_plugins: 热门插件列表
        last_scan: 最后扫描时间（已废弃，恒为None）
    """

    total: int = 0
    enabled: int = 0
    with_smart_tools: int = 0
    total_commands: int = 0
    total_tools: int = 0
    hot_plugins: list[dict[str, Any]] = field(default_factory=list)
    last_scan: datetime | None = None
