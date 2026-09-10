"""插件知识库管理器

直接复用 help 插件 HelpManage 提供的插件查询接口获取插件信息，
提供知识库查询接口：按名称查询/列表/关键词智能召回，
基于用户输入文本智能召回相关插件，构建供AI读取的知识块。
含查询日志记录与内存缓存优化。

完全依赖流萤本体插件系统，不再维护AI插件独立的插件知识表。
"""

from datetime import datetime, timedelta
import re
from typing import Any

from liuying.liuying_plugins.help.data_source import HelpManage
from liuying.services.cache import CacheDict
from liuying.utils.log import logger

from ...models.knowledge_query_log import KnowledgeQueryLog
from .types import KnowledgeStats, RecallResult

_MAX_QUERY_LOG_LENGTH = 500
"""查询日志文本最大长度"""

_CACHE_TTL_SECONDS = 300
"""内存缓存TTL（秒）"""

_MAX_RECALL_RESULTS = 8
"""单次召回最大结果数"""

_STOPWORDS: set[str] = {
    "的", "了", "是", "在", "我", "你", "他", "她", "它",
    "请", "帮", "能", "可以", "吗", "么", "啊", "呢", "吧",
    "一下", "帮我", "请问", "怎么", "如何", "什么", "为什么",
    "the", "a", "an", "is", "are", "to", "of",
}
"""召回分词停用词集合（高频无意义词）"""

_NON_WORD_RE = re.compile(r"[^\w\u4e00-\u9fa5]+")
"""非词元字符匹配模式（模块级预编译，避免每次分词重复解析）"""


def tokenize(text: str) -> list[str]:
    """分词（简化的中英文混合分词）

    参数:
        text: 输入文本

    返回:
        list[str]: 分词后的token列表（去停用词、去重）
    """
    if not text:
        return []
    cleaned = _NON_WORD_RE.sub(" ", text)
    tokens: list[str] = []
    seen: set[str] = set()

    for raw in cleaned.split():
        token = raw.strip().lower()
        if not token or token in _STOPWORDS:
            continue
        if len(token) < 2 and not token.isascii():
            continue
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)

    for i in range(len(cleaned)):
        if not ("\u4e00" <= cleaned[i] <= "\u9fa5"):
            continue
        for length in (2, 3, 4):
            end = i + length
            if end > len(cleaned):
                break
            piece = cleaned[i:end]
            if any(not ("\u4e00" <= c <= "\u9fa5") for c in piece):
                continue
            token = piece.lower()
            if token in _STOPWORDS or token in seen:
                continue
            seen.add(token)
            tokens.append(token)
    return tokens


class KnowledgeStore:
    """插件知识库管理器（复用 help 插件查询接口）

    通过 HelpManage 获取插件列表与完整信息，
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

    async def _get_list(self) -> list[dict[str, Any]]:
        """获取插件摘要列表（带缓存）

        返回:
            list[dict[str, Any]]: HelpManage.get_plugin_list 结果
        """
        cached = self._cache.get("plugin_list")
        if cached is not None:
            return cached
        plugins = await HelpManage.get_plugin_list()
        self._cache.set("plugin_list", plugins)
        return plugins

    async def get_by_name(self, plugin_name: str) -> dict[str, Any] | None:
        """按插件名称/模块名/id查询完整信息

        参数:
            plugin_name: 插件名称、模块名或id

        返回:
            dict[str, Any] | None: 插件完整信息或None
        """
        if not plugin_name:
            return None
        cache_key = f"full:{plugin_name}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        info = await HelpManage.get_plugin_full_info(plugin_name)
        if info is None:
            info = await self._resolve_by_list(plugin_name)
        if info is not None:
            self._cache.set(cache_key, info)
        return info

    async def _resolve_by_list(
        self, plugin_name: str
    ) -> dict[str, Any] | None:
        """通过插件列表模糊解析插件（别名/忽略大小写）

        参数:
            plugin_name: 插件名称或别名

        返回:
            dict[str, Any] | None: 插件完整信息或None
        """
        lowered = plugin_name.lower()
        for item in await self._get_list():
            name = str(item.get("name") or "")
            if name.lower() == lowered or lowered in [
                str(a).lower() for a in item.get("aliases") or []
            ]:
                return await HelpManage.get_plugin_full_info(
                    str(item.get("module") or name)
                )
        return None

    async def list_enabled(
        self,
        menu_type: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """列出可见插件

        参数:
            menu_type: 菜单类型过滤，None时不过滤
            limit: 返回上限

        返回:
            list[dict[str, Any]]: 插件摘要列表
        """
        plugins = await self._get_list()
        if menu_type:
            plugins = [
                p for p in plugins if p.get("menu_type") == menu_type
            ]
        return plugins[:limit]

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

        tokens = tokenize(text)
        if not tokens:
            return []

        all_items = await self._get_list()
        if not all_items:
            return []

        results: list[RecallResult] = []
        for item in all_items:
            score, matched = self._score_item(item, tokens)
            if score > 0:
                results.append(
                    RecallResult(info=item, score=score, matched_fields=matched)
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
        item: dict[str, Any],
        tokens: list[str],
    ) -> tuple[float, list[str]]:
        """为单个插件条目计算匹配评分

        参数:
            item: 插件摘要字典
            tokens: 分词后的token列表

        返回:
            tuple[float, list[str]]: (评分, 命中字段列表)
        """
        score = 0.0
        matched: list[str] = []
        display = str(item.get("name") or "").lower()
        module = str(item.get("module") or "").lower()
        desc = str(item.get("description") or "").lower()
        aliases = [str(a).lower() for a in item.get("aliases") or []]

        command_strs: list[str] = []
        for cmd in item.get("commands") or []:
            cmd_text = str(cmd.get("command") or "").lower()
            if cmd_text:
                command_strs.append(cmd_text)
            for ex in cmd.get("examples") or []:
                ex_text = str(ex.get("exec") or "").lower()
                if ex_text:
                    command_strs.append(ex_text)

        for token in tokens:
            if token in display or token in module:
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
        primary = str(results[0].info.get("module") or "") if results else ""
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

    @staticmethod
    def build_detail_block(info: dict[str, Any]) -> str:
        """构建供AI读取的单个插件知识块文本

        参数:
            info: 插件完整信息字典（get_plugin_full_info 结果）

        返回:
            str: 格式化的知识块文本
        """
        parts: list[str] = [
            f"## {info.get('name') or info.get('module')}",
            f"模块: {info.get('module')}",
        ]
        if description := str(info.get("description") or ""):
            parts.append(f"描述: {description}")
        if menu_type := str(info.get("menu_type") or ""):
            parts.append(f"分类: {menu_type}")
        if usage := str(info.get("usage") or ""):
            parts.append(f"用法: {usage}")

        commands = info.get("commands") or []
        if commands:
            parts.append("命令:")
            for cmd in commands:
                line = f"- {cmd.get('command', '')}"
                params = cmd.get("params") or []
                if params:
                    line += " " + " ".join(f"[{p}]" for p in params)
                if desc := str(cmd.get("description") or ""):
                    line += f": {desc}"
                parts.append(line)

        tools = info.get("smart_tools") or []
        if tools:
            parts.append("AI工具:")
            for tool in tools:
                parts.append(
                    f"- {tool.get('name', '')}: {tool.get('description', '')}"
                )

        return "\n".join(parts)

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
            blocks.append(self.build_detail_block(r.info))
        blocks.append(
            "提示：如需调用上述插件能力，请通过命令提示用户或"
            "在回复中引用对应命令；不要伪造不存在的命令。"
        )
        return "\n\n".join(blocks)

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

        all_items = await self._get_list()
        total_commands = sum(
            len(item.get("commands") or []) for item in all_items
        )
        total_tools = sum(
            int(item.get("tools_count") or 0) for item in all_items
        )
        enabled_count = sum(1 for item in all_items if item.get("status"))
        with_tools_count = sum(
            1 for item in all_items if int(item.get("tools_count") or 0) > 0
        )

        hot = await KnowledgeQueryLog.get_hot_plugins(
            days=7, limit=10
        )

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

    async def prune_stale(self, days: int = 30) -> int:
        """清理过期查询日志

        参数:
            days: 保留天数

        返回:
            int: 清理的记录数
        """
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


knowledge_store = KnowledgeStore()
"""知识库管理器单例"""
