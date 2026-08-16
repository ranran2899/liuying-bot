"""证据合成器

将多工具调用结果合成为结构化证据，规划证据使用策略，
渲染证据指导提示。参考 nonebot_plugin_personification 的
evidence.py 设计，增强为 EvidenceSynthesis 结构化合成：
- 记忆选择与过滤（防冒犯风险）
- 工具证据摘要（200字内）
- 不确定性标注
- 是否需要更多研究的判断
"""

from dataclasses import dataclass, field
import time
from typing import Any

from .constants import EVIDENCE_KIND_CONTEXT, EVIDENCE_KIND_TOOL

# 可重试的查询类工具（空结果时可换变体重试）
RETRYABLE_LOOKUP_TOOLS: set[str] = {
    "web_search",
    "fetch_webpage",
    "search_plugin_knowledge",
    "search_plugin_by_capability",
}
"""空结果可重试工具白名单"""

_EMPTY_RESULT_MARKERS: tuple[str, ...] = (
    "未找到",
    "没有找到",
    "无结果",
    "no_results",
    "暂无",
    "搜索失败",
    "未检索到",
)
"""空结果文本标记"""

_MAX_EVIDENCE_ITEMS = 6
"""合成时最多保留的证据条数"""

_MAX_DIGEST_CHARS = 200
"""工具证据摘要最大字符数"""

_MAX_MEMORY_ITEMS = 5
"""最多选择的记忆条数"""


@dataclass(slots=True)
class EvidenceItem:
    """单条证据

    Attributes:
        kind: 证据类型（tool/context/memory）
        source: 来源（工具名或上下文描述）
        content: 证据内容
        relevance: 相关性评分（0-1）
        timestamp: 时间戳
        metadata: 附加元信息
    """

    kind: str
    source: str
    content: str
    relevance: float = 0.5
    timestamp: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EvidenceSynthesis:
    """结构化证据合成结果

    供响应器消费，指导最终回复生成。

    Attributes:
        memory_ids: 选中的记忆ID列表
        memory_inject_style: 记忆注入风格（factual/softened/drop）
        tool_digest: 工具证据摘要（200字内）
        uncertainty_notes: 不确定点列表
        needs_more_research: 是否需要更多研究
        research_followup_query: 后续研究查询
    """

    memory_ids: list[str] = field(default_factory=list)
    memory_inject_style: str = "factual"
    tool_digest: str = ""
    uncertainty_notes: list[str] = field(default_factory=list)
    needs_more_research: bool = False
    research_followup_query: str = ""


class EvidenceComposer:
    """证据合成器

    收集多工具调用结果与上下文证据，合成LLM可用的结构化证据。
    支持空结果识别、冲突检测、token预算感知的摘要生成。
    """

    def __init__(self) -> None:
        """初始化证据合成器"""
        self._items: list[EvidenceItem] = []
        self._memory_candidates: list[dict[str, Any]] = []

    def add_tool_evidence(
        self,
        tool_name: str,
        result: str,
        relevance: float = 0.7,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """添加工具证据

        参数:
            tool_name: 工具名
            result: 工具结果
            relevance: 相关性评分
            metadata: 附加元信息
        """
        self._items.append(
            EvidenceItem(
                kind=EVIDENCE_KIND_TOOL,
                source=tool_name,
                content=result,
                relevance=relevance,
                timestamp=time.time(),
                metadata=metadata or {},
            )
        )

    def add_context_evidence(
        self,
        source: str,
        content: str,
        relevance: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """添加上下文证据

        参数:
            source: 来源描述
            content: 证据内容
            relevance: 相关性评分
            metadata: 附加元信息
        """
        self._items.append(
            EvidenceItem(
                kind=EVIDENCE_KIND_CONTEXT,
                source=source,
                content=content,
                relevance=relevance,
                timestamp=time.time(),
                metadata=metadata or {},
            )
        )

    def add_memory_candidates(
        self, memories: list[dict[str, Any]]
    ) -> None:
        """添加候选记忆供合成时选择

        参数:
            memories: 候选记忆列表，每项含id/summary等字段
        """
        self._memory_candidates = list(memories)

    def compose(self, max_items: int = _MAX_EVIDENCE_ITEMS) -> str:
        """合成证据文本

        按相关性排序，取top-N合成文本。图片生成工具证据特殊处理。

        参数:
            max_items: 最大证据数量

        返回:
            str: 合成的证据文本
        """
        if not self._items:
            return ""
        sorted_items = sorted(
            self._items, key=lambda x: x.relevance, reverse=True
        )
        selected = sorted_items[:max_items]
        return self._render_evidence(selected)

    def synthesize(self) -> EvidenceSynthesis:
        """合成结构化证据（无需LLM的规则版本）

        基于规则选择记忆、生成摘要、标注不确定性。
        LLM版本可在响应器中按需调用。

        返回:
            EvidenceSynthesis: 结构化证据
        """
        # 记忆选择：取前N条，过滤高风险记忆
        selected_memory_ids: list[str] = []
        for mem in self._memory_candidates[:_MAX_MEMORY_ITEMS]:
            mem_id = str(mem.get("id", "") or "").strip()
            if not mem_id:
                continue
            tone_risk = float(mem.get("tone_risk", 0.0) or 0.0)
            irony_risk = float(mem.get("irony_risk", 0.0) or 0.0)
            if tone_risk >= 0.6 or irony_risk >= 0.6:
                continue
            selected_memory_ids.append(mem_id)

        # 工具证据摘要
        tool_items = [
            i for i in self._items if i.kind == EVIDENCE_KIND_TOOL
        ]
        digest = self._build_tool_digest(tool_items)

        # 不确定性标注
        uncertainties = self._detect_uncertainties(tool_items)

        # 是否需要更多研究：有空结果工具且可重试
        needs_more = any(
            self._is_empty_result(i.content)
            and i.source in RETRYABLE_LOOKUP_TOOLS
            for i in tool_items
        )

        return EvidenceSynthesis(
            memory_ids=selected_memory_ids,
            memory_inject_style="factual" if selected_memory_ids else "drop",
            tool_digest=digest,
            uncertainty_notes=uncertainties,
            needs_more_research=needs_more,
        )

    def _build_tool_digest(
        self, items: list[EvidenceItem]
    ) -> str:
        """构建工具证据摘要

        每条工具结果取前80字，总摘要控制在200字内。

        参数:
            items: 工具证据列表

        返回:
            str: 摘要文本
        """
        if not items:
            return ""
        parts: list[str] = []
        total = 0
        for item in items[:4]:
            content = item.content.strip()
            if not content or self._is_empty_result(content):
                continue
            snippet = content[:80]
            parts.append(f"[{item.source}] {snippet}")
            total += len(snippet)
            if total >= _MAX_DIGEST_CHARS:
                break
        return " | ".join(parts)[:_MAX_DIGEST_CHARS]

    def _detect_uncertainties(
        self, items: list[EvidenceItem]
    ) -> list[str]:
        """检测证据中的不确定点

        参数:
            items: 工具证据列表

        返回:
            list[str]: 不确定点描述
        """
        notes: list[str] = []
        for item in items:
            if self._is_empty_result(item.content):
                notes.append(f"{item.source}返回空结果")
            elif "可能" in item.content or "不确定" in item.content:
                notes.append(f"{item.source}含不确定信息")
        return notes

    def _is_empty_result(self, text: str) -> bool:
        """判断工具结果是否为空

        参数:
            text: 工具结果文本

        返回:
            bool: 是否为空结果
        """
        if not text or not text.strip():
            return True
        lowered = text.strip().lower()
        return any(marker in lowered for marker in _EMPTY_RESULT_MARKERS)

    def _render_evidence(self, items: list[EvidenceItem]) -> str:
        """渲染证据为文本

        图片生成工具的证据仅显示为占位描述，避免LLM在文字中重复URL。

        参数:
            items: 证据列表

        返回:
            str: 渲染后的文本
        """
        if not items:
            return ""
        lines = ["[已收集证据]"]
        for i, item in enumerate(items, 1):
            kind_label = "工具" if item.kind == EVIDENCE_KIND_TOOL else "上下文"
            content = item.content
            if (
                item.kind == EVIDENCE_KIND_TOOL
                and item.source == "image_generate"
                and item.metadata.get("output_kind") == "image_url"
            ):
                content = "已生成图片，将以图片消息形式发送"
            lines.append(f"{i}. [{kind_label}|{item.source}] {content}")
        return "\n".join(lines)

    def build_evidence_guidance(self) -> str:
        """构建证据使用指导提示

        返回:
            str: 证据指导文本
        """
        synthesis = self.synthesize()
        if not self._items and not synthesis.memory_ids:
            return ""
        lines: list[str] = []
        tool_count = sum(
            1 for i in self._items if i.kind == EVIDENCE_KIND_TOOL
        )
        ctx_count = sum(
            1 for i in self._items if i.kind == EVIDENCE_KIND_CONTEXT
        )
        lines.append(
            f"已收集 {tool_count} 条工具证据和 {ctx_count} 条上下文证据。"
        )
        if synthesis.tool_digest:
            lines.append(f"证据摘要：{synthesis.tool_digest}")
        if synthesis.uncertainty_notes:
            lines.append(
                "不确定点："
                + "; ".join(synthesis.uncertainty_notes[:3])
            )
        if synthesis.needs_more_research:
            lines.append("注意：部分查询返回空结果，可能需要补充查证。")
        lines.extend([
            "请基于上述证据回复用户，注意：",
            "1. 优先使用相关性高的证据",
            "2. 不要暴露工具调用细节",
            "3. 用角色口吻自然表达",
            "4. 未调用工具且不确定时禁止编造具体数字/链接/日期",
        ])
        return "\n".join(lines)

    def clear(self) -> None:
        """清空证据"""
        self._items.clear()
        self._memory_candidates.clear()

    @property
    def items(self) -> list[EvidenceItem]:
        """获取所有证据项"""
        return list(self._items)


__all__ = [
    "RETRYABLE_LOOKUP_TOOLS",
    "EvidenceComposer",
    "EvidenceItem",
    "EvidenceSynthesis",
]
