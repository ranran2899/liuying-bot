"""插件知识库管理器

基于 PluginInfo + NoneBot 实时元信息构建插件视图，
提供知识库查询接口：按名称/关键词/菜单类型多维度检索，
基于用户输入文本智能召回相关插件，构建供AI读取的知识块。
含查询日志记录与内存缓存优化。

完全依赖流萤本体插件系统，不再维护AI插件独立的插件知识表。
"""

from datetime import datetime, timedelta
from typing import Any

import nonebot
from nonebot.plugin import Plugin, PluginMetadata

from liuying.models.plugin_info import PluginInfo
from liuying.services.cache import CacheDict
from liuying.utils.enum import PluginType
from liuying.utils.log import logger

from ...models.knowledge_query_log import KnowledgeQueryLog
from .extractors import (
    _build_keywords,
    _extract_aliases,
    _extract_commands,
    _extract_smart_tools,
    _tokenize,
)
from .types import KnowledgeStats, RecallResult

_MAX_QUERY_LOG_LENGTH = 500
"""查询日志文本最大长度"""

_CACHE_TTL_SECONDS = 300
"""内存缓存TTL（秒）"""

_MAX_RECALL_RESULTS = 8
"""单次召回最大结果数"""


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
            except Exception:
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
        return _build_keywords(
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
        return _extract_commands(self._extra)

    def get_smart_tools(self) -> list[dict[str, Any]]:
        """解析AI工具标签

        返回:
            list[dict]: 工具标签字典列表
        """
        return _extract_smart_tools(self._extra)

    def get_aliases(self) -> list[str]:
        """解析别名

        返回:
            list[str]: 别名列表
        """
        return _extract_aliases(self._extra)

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


class KnowledgeStore:
    """插件知识库管理器（基于流萤本体插件系统）

    通过 PluginInfo + NoneBot 实时元信息构建插件视图，
    提供多维度检索、智能召回、知识块构建、查询日志、缓存等。
    单例模式，由 knowledge_store 单例导出。
    """

    def __init__(self) -> None:
        """初始化知识库管理器"""
        self._cache = CacheDict(
            "AI_KNOWLEDGE_STORE", expire=_CACHE_TTL_SECONDS, max_size=256
        )
        """内存缓存：key -> 值（300秒TTL，最多256条）"""
        self._last_stats: KnowledgeStats | None = None
        """缓存的统计数据"""
        self._last_stats_time: float = 0.0
        """统计缓存时间"""

    def _cache_get(self, key: str) -> Any | None:
        """从缓存获取

        参数:
            key: 缓存键

        返回:
            Any | None: 缓存值或None
        """
        return self._cache.get(key)

    def _cache_set(self, key: str, value: Any) -> None:
        """设置缓存

        参数:
            key: 缓存键
            value: 缓存值
        """
        self._cache.set(key, value)

    def invalidate_cache(self) -> None:
        """清空缓存（插件状态变更后调用）"""
        self._cache.clear()
        self._last_stats = None
        self._last_stats_time = 0.0

    async def _build_view(self, info: PluginInfo) -> PluginView:
        """构建插件视图

        参数:
            info: PluginInfo 数据库记录

        返回:
            PluginView: 插件视图（含实时元信息）
        """
        nb_plugin = nonebot.get_plugin_by_module_name(info.module_path)
        return PluginView(info, nb_plugin)

    async def get_by_name(
        self, plugin_name: str
    ) -> PluginView | None:
        """按插件模块名查询

        参数:
            plugin_name: 插件模块名

        返回:
            PluginView | None: 插件视图或None
        """
        if not plugin_name:
            return None
        cache_key = f"name:{plugin_name}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        info = await PluginInfo.filter(
            module=plugin_name
        ).first()
        if info is None:
            return None
        view = await self._build_view(info)
        self._cache_set(cache_key, view)
        return view

    async def list_enabled(
        self,
        menu_type: str | None = None,
        limit: int = 200,
    ) -> list[PluginView]:
        """列出启用的插件

        参数:
            menu_type: 菜单类型过滤，None时不过滤
            limit: 返回上限

        返回:
            list[PluginView]: 插件视图列表
        """
        cache_key = f"list:{menu_type or 'all'}:{limit}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        query = PluginInfo.filter(
            load_status=True,
            is_show=True,
            is_delete=False,
        ).filter(PluginInfo.plugin_type != PluginType.PARENT)
        infos = await query.limit(limit).all()
        views: list[PluginView] = []
        for info in infos:
            view = await self._build_view(info)
            if menu_type and view.menu_type != menu_type:
                continue
            views.append(view)
        self._cache_set(cache_key, views)
        return views

    async def search_by_keyword(
        self, keyword: str, limit: int = 10
    ) -> list[PluginView]:
        """关键词搜索

        参数:
            keyword: 关键词
            limit: 返回上限

        返回:
            list[PluginView]: 匹配的插件视图列表
        """
        if not keyword:
            return []
        all_items = await self.list_enabled(limit=500)
        results: list[PluginView] = []
        kw = keyword.lower()
        for item in all_items:
            if (
                kw in (item.keywords or "").lower()
                or kw in (item.display_name or "").lower()
                or kw in (item.description or "").lower()
            ):
                results.append(item)
                if len(results) >= limit:
                    break
        return results

    async def recall(
        self,
        text: str,
        top_k: int = _MAX_RECALL_RESULTS,
        *,
        user_id: str = "",
        group_id: str = "",
        log_query: bool = True,
    ) -> list[RecallResult]:
        """基于用户文本智能召回相关插件

        多维度评分：关键词命中、别名命中、命令名命中、显示名命中。
        评分越高越相关。

        参数:
            text: 用户输入文本
            top_k: 返回数量上限
            user_id: 用户ID（用于日志）
            group_id: 群组ID（用于日志）
            log_query: 是否记录查询日志

        返回:
            list[RecallResult]: 召回结果列表
        """
        if not text or not text.strip():
            return []

        tokens = _tokenize(text)
        if not tokens:
            return []

        all_items = await self.list_enabled(limit=500)
        if not all_items:
            return []

        results: list[RecallResult] = []
        for item in all_items:
            score, matched = self._score_item(item, tokens, text)
            if score > 0:
                results.append(
                    RecallResult(
                        plugin=item, score=score, matched_fields=matched
                    )
                )

        results.sort(key=lambda r: r.score, reverse=True)
        top = results[:top_k]

        if log_query and top:
            await self._log_recall(
                text=text,
                results=top,
                user_id=user_id,
                group_id=group_id,
            )

        return top

    def _score_item(
        self,
        item: PluginView,
        tokens: list[str],
        raw_text: str,
    ) -> tuple[float, list[str]]:
        """为单个插件条目计算匹配评分

        参数:
            item: 插件视图
            tokens: 分词后的token列表
            raw_text: 原始文本

        返回:
            tuple[float, list[str]]: (评分, 命中字段列表)
        """
        del raw_text
        score = 0.0
        matched: list[str] = []
        keywords_str = (item.keywords or "").lower()
        display = (item.display_name or "").lower()
        desc = (item.description or "").lower()
        aliases = [a.lower() for a in item.get_aliases()]

        commands = item.get_commands()
        command_strs: list[str] = []
        for cmd in commands:
            cmd_text = (cmd.get("command", "") or "").lower()
            if cmd_text:
                command_strs.append(cmd_text)
            for ex in cmd.get("examples", []):
                if isinstance(ex, dict):
                    ex_text = str(ex.get("exec", "") or "").lower()
                else:
                    ex_text = str(
                        getattr(ex, "exec", "") or ""
                    ).lower()
                if ex_text:
                    command_strs.append(ex_text)

        for token in tokens:
            if token in keywords_str:
                score += 3.0
                if "keywords" not in matched:
                    matched.append("keywords")
            if token in display:
                score += 2.5
                if "display_name" not in matched:
                    matched.append("display_name")
            if token in desc:
                score += 1.5
                if "description" not in matched:
                    matched.append("description")
            for alias in aliases:
                if token in alias or alias in token:
                    score += 2.0
                    if "aliases" not in matched:
                        matched.append("aliases")
                    break
            for cmd_str in command_strs:
                if token in cmd_str or cmd_str in token:
                    score += 2.0
                    if "commands" not in matched:
                        matched.append("commands")
                    break

        return score, matched

    async def _log_recall(
        self,
        text: str,
        results: list[RecallResult],
        user_id: str,
        group_id: str,
    ) -> None:
        """记录召回日志

        参数:
            text: 原始查询文本
            results: 召回结果列表
            user_id: 用户ID
            group_id: 群组ID
        """
        try:
            primary = results[0].plugin.plugin_name if results else ""
            await KnowledgeQueryLog.add_log(
                query_text=text[:_MAX_QUERY_LOG_LENGTH],
                matched_plugin=primary,
                user_id=user_id,
                group_id=group_id,
                extra={
                    "matched_count": len(results),
                    "top_score": (
                        round(results[0].score, 3) if results else 0.0
                    ),
                },
            )
        except Exception as e:
            logger.debug(
                f"记录知识库查询日志失败: {e}",
                command="AI",
                e=e,
            )

    async def build_prompt_block(
        self,
        text: str,
        top_k: int = 3,
        *,
        user_id: str = "",
        group_id: str = "",
    ) -> str:
        """构建供AI读取的知识块文本

        基于用户文本召回相关插件，拼接成知识块。

        参数:
            text: 用户输入文本
            top_k: 召回数量
            user_id: 用户ID
            group_id: 群组ID

        返回:
            str: 知识块文本（无召回时返回空串）
        """
        results = await self.recall(
            text,
            top_k=top_k,
            user_id=user_id,
            group_id=group_id,
        )
        if not results:
            return ""

        blocks: list[str] = [
            "## 可用插件知识（用户提问可能相关）"
        ]
        for r in results:
            blocks.append(r.plugin.build_prompt_block())
        blocks.append(
            "提示：如需调用上述插件能力，请通过命令提示用户或"
            "在回复中引用对应命令；不要伪造不存在的命令。"
        )
        return "\n\n".join(blocks)

    async def build_full_catalog_block(
        self, menu_type: str | None = None
    ) -> str:
        """构建完整插件目录块（供AI总览）

        参数:
            menu_type: 菜单类型过滤，None时不过滤

        返回:
            str: 目录块文本
        """
        items = await self.list_enabled(menu_type=menu_type, limit=300)
        if not items:
            return "（暂无可用插件）"

        by_menu: dict[str, list[PluginView]] = {}
        for item in items:
            by_menu.setdefault(item.menu_type or "其他", []).append(item)

        parts: list[str] = ["## 插件目录总览"]
        for menu, group in sorted(by_menu.items()):
            parts.append(f"\n### {menu}")
            for item in group:
                line = f"- {item.display_name or item.plugin_name}"
                if item.description:
                    line += f": {item.description[:80]}"
                parts.append(line)
        return "\n".join(parts)

    async def get_stats(self) -> KnowledgeStats:
        """获取知识库统计

        返回:
            KnowledgeStats: 统计数据
        """
        now_ts = datetime.now().timestamp()
        if (
            self._last_stats
            and now_ts - self._last_stats_time < _CACHE_TTL_SECONDS
        ):
            return self._last_stats

        all_items = await self.list_enabled(limit=500)
        total_commands = 0
        total_tools = 0
        enabled_count = 0
        with_tools_count = 0

        for item in all_items:
            cmds = item.get_commands()
            tools = item.get_smart_tools()
            total_commands += len(cmds)
            total_tools += len(tools)
            if item.is_enabled:
                enabled_count += 1
            if tools:
                with_tools_count += 1

        try:
            hot = await KnowledgeQueryLog.get_hot_plugins(
                days=7, limit=10
            )
        except Exception:
            hot = []

        stats = KnowledgeStats(
            total=len(all_items),
            enabled=enabled_count,
            with_smart_tools=with_tools_count,
            total_commands=total_commands,
            total_tools=total_tools,
            hot_plugins=hot,
            last_scan=None,
        )
        self._last_stats = stats
        self._last_stats_time = now_ts
        return stats

    async def get_hot_plugins(
        self, days: int = 7, limit: int = 10
    ) -> list[dict[str, Any]]:
        """获取热门插件

        参数:
            days: 统计天数
            limit: 返回上限

        返回:
            list[dict]: 热门插件列表
        """
        try:
            return await KnowledgeQueryLog.get_hot_plugins(
                days=days, limit=limit
            )
        except Exception as e:
            logger.debug(
                f"获取热门插件失败: {e}", command="AI", e=e
            )
            return []

    async def set_plugin_enabled(
        self, plugin_name: str, enabled: bool
    ) -> None:
        """设置插件启用状态

        通过更新 PluginInfo.status 实现。

        参数:
            plugin_name: 插件模块名
            enabled: 是否启用
        """
        info = await PluginInfo.filter(
            module=plugin_name
        ).first()
        if info is None:
            return
        info.status = enabled
        await info.save(update_fields=["status"])
        self.invalidate_cache()

    async def prune_stale(self, days: int = 30) -> int:
        """清理过期查询日志

        参数:
            days: 保留天数

        返回:
            int: 清理的记录数
        """
        try:
            since = datetime.now() - timedelta(days=days)
            old_logs = await KnowledgeQueryLog.filter(
                query_time__lt=since
            ).limit(5000).all()
            count = 0
            for log in old_logs:
                await log.delete()
                count += 1
            if count > 0:
                logger.info(
                    f"清理过期知识库查询日志: {count} 条",
                    command="AI",
                )
            return count
        except Exception as e:
            logger.debug(
                f"清理查询日志失败: {e}", command="AI", e=e
            )
            return 0


knowledge_store = KnowledgeStore()
"""知识库管理器单例"""
