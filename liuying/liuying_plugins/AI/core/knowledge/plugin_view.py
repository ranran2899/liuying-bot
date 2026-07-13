"""插件视图

PluginInfo + NoneBot 实时元信息的组合视图，
统一暴露插件名/描述/命令/AI工具/别名等字段供AI检索。
所有属性在访问时即时计算，确保数据始终为最新。
"""

from typing import Any

from nonebot.plugin import Plugin, PluginMetadata

from liuying.models.plugin_info import PluginInfo

from .extractors import KnowledgeExtractor


class PluginView:
    """插件视图：PluginInfo + NoneBot 实时元信息的组合视图

    统一暴露插件名/描述/命令/AI工具/别名等字段供AI检索。
    所有属性在访问时即时计算，确保数据始终为最新。
    """

    __slots__ = ("_extra", "_info", "_meta", "_nb_plugin")

    def __init__(
        self,
        plugin_info: PluginInfo,
        nb_plugin: Plugin | None,
    ) -> None:
        """初始化插件视图

        参数:
            plugin_info: 数据库插件信息
            nb_plugin: NoneBot Plugin 实例（None表示插件已卸载）
        """
        self._info = plugin_info
        self._nb_plugin = nb_plugin
        meta: PluginMetadata | None = None
        if nb_plugin is not None:
            meta = getattr(nb_plugin, "__plugin_meta__", None)
        self._meta = meta
        extra_raw = getattr(meta, "extra", None) or {}
        if not isinstance(extra_raw, dict):
            try:
                extra_raw = dict(extra_raw)
            except (TypeError, ValueError):
                extra_raw = {}
        self._extra = extra_raw

    @property
    def id(self) -> int:
        """数据库主键ID"""
        return self._info.id

    @property
    def plugin_name(self) -> str:
        """插件模块名（唯一标识）"""
        return self._info.module

    @property
    def display_name(self) -> str:
        """插件显示名"""
        if self._meta and getattr(self._meta, "name", ""):
            return str(self._meta.name)
        return self._info.name

    @property
    def description(self) -> str:
        """插件描述"""
        if self._meta:
            return str(getattr(self._meta, "description", "") or "")
        return ""

    @property
    def module_path(self) -> str:
        """模块路径"""
        return self._info.module_path

    @property
    def version(self) -> str:
        """插件版本"""
        v = self._extra.get("version")
        if v:
            return str(v)
        return self._info.version or ""

    @property
    def author(self) -> str:
        """作者"""
        a = self._extra.get("author")
        if a:
            return str(a)
        return self._info.author or ""

    @property
    def menu_type(self) -> str:
        """菜单类型"""
        mt = self._extra.get("menu_type")
        if mt:
            return str(mt)
        return self._info.menu_type or "功能"

    @property
    def plugin_type(self) -> str:
        """插件类型"""
        pt = self._info.plugin_type
        if pt is None:
            return "normal"
        return str(getattr(pt, "value", pt) or "normal")

    @property
    def is_show(self) -> bool:
        """是否显示在菜单"""
        return bool(self._extra.get("is_show", True)) and self._info.is_show

    @property
    def is_enabled(self) -> bool:
        """是否启用（数据库status + load_status + 未删除）"""
        return bool(
            self._info.status
            and self._info.load_status
            and not self._info.is_delete
        )

    @property
    def summary(self) -> str:
        """LLM增强摘要（不再支持，恒为空串）"""
        return ""

    @property
    def keywords(self) -> str:
        """检索关键词（动态计算）"""
        return KnowledgeExtractor.build_keywords(
            display_name=self.display_name,
            description=self.description,
            commands=self.get_commands(),
            aliases=self.get_aliases(),
            menu_type=self.menu_type,
        )

    @property
    def superuser_help(self) -> str:
        """超级用户帮助"""
        return str(self._extra.get("superuser_help", "") or "")

    @property
    def usage_text(self) -> str:
        """用法说明"""
        if self._meta:
            return str(getattr(self._meta, "usage", "") or "")
        return ""

    def get_commands(self) -> list[dict[str, Any]]:
        """解析命令列表

        返回:
            list[dict]: 命令字典列表
        """
        return KnowledgeExtractor.extract_commands(self._extra)

    def get_smart_tools(self) -> list[dict[str, Any]]:
        """解析AI工具标签

        返回:
            list[dict]: 工具标签字典列表
        """
        return KnowledgeExtractor.extract_smart_tools(self._extra)

    def get_aliases(self) -> list[str]:
        """解析别名

        返回:
            list[str]: 别名列表
        """
        return KnowledgeExtractor.extract_aliases(self._extra)

    def get_extra(self) -> dict[str, Any]:
        """解析额外信息

        返回:
            dict: 额外信息字典
        """
        return self._extra

    def to_brief(self) -> dict[str, Any]:
        """导出简要信息（供AI检索结果）

        返回:
            dict: 简要信息字典
        """
        return {
            "plugin_name": self.plugin_name,
            "display_name": self.display_name,
            "description": self.description,
            "menu_type": self.menu_type,
            "version": self.version,
            "summary": self.summary or self.description,
            "commands": self.get_commands(),
            "aliases": self.get_aliases(),
            "is_enabled": self.is_enabled,
        }

    def to_full(self) -> dict[str, Any]:
        """导出完整信息（供AI深度调用）

        返回:
            dict: 完整信息字典
        """
        brief = self.to_brief()
        brief.update(
            {
                "smart_tools": self.get_smart_tools(),
                "superuser_help": self.superuser_help,
                "usage_text": self.usage_text,
                "keywords": self.keywords,
                "extra": self.get_extra(),
            }
        )
        return brief

    def build_prompt_block(self) -> str:
        """构建供AI读取的知识块文本

        返回:
            str: 格式化的知识块文本
        """
        parts: list[str] = [
            f"## {self.display_name or self.plugin_name}",
            f"模块: {self.plugin_name}",
        ]
        if self.description:
            parts.append(f"描述: {self.description}")
        if self.menu_type:
            parts.append(f"分类: {self.menu_type}")

        commands = self.get_commands()
        if commands:
            parts.append("命令:")
            for cmd in commands:
                line = f"- {cmd.get('command', '')}"
                params = cmd.get("params", [])
                if params:
                    line += " " + " ".join(
                        f"[{p}]" for p in params
                    )
                desc = cmd.get("description", "")
                if desc:
                    line += f": {desc}"
                parts.append(line)

        tools = self.get_smart_tools()
        if tools:
            parts.append("AI工具:")
            for tool in tools:
                name = tool.get("name", "")
                desc = tool.get("description", "")
                parts.append(f"- {name}: {desc}")

        return "\n".join(parts)
