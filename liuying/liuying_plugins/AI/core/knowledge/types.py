"""知识库数据类型

定义召回结果与知识库统计的数据结构，
召回结果直接承载 help 插件查询接口返回的插件信息字典。
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RecallResult:
    """召回结果

    属性:
        info: 插件摘要信息字典（HelpManage.get_plugin_list 单项）
        score: 匹配评分
        matched_fields: 命中字段列表
    """

    info: dict[str, Any]
    score: float = 0.0
    matched_fields: list[str] = field(default_factory=list)

    def to_brief(self) -> dict[str, Any]:
        """导出简要信息

        返回:
            dict: 简要信息字典（含评分）
        """
        brief = {
            "plugin_name": str(self.info.get("module") or ""),
            "display_name": str(self.info.get("name") or ""),
            "description": str(self.info.get("description") or ""),
            "menu_type": str(self.info.get("menu_type") or ""),
            "commands": list(self.info.get("commands") or []),
            "aliases": list(self.info.get("aliases") or []),
            "is_enabled": bool(self.info.get("status")),
        }
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
    """

    total: int = 0
    enabled: int = 0
    with_smart_tools: int = 0
    total_commands: int = 0
    total_tools: int = 0
    hot_plugins: list[dict[str, Any]] = field(default_factory=list)
