"""证据合成器

将多工具调用结果合成为LLM可用的结构化证据，规划证据使用策略，
渲染证据指导提示。
"""

from dataclasses import dataclass, field
import time
from typing import Any

from ..constants import EVIDENCE_KIND_CONTEXT, EVIDENCE_KIND_TOOL


@dataclass(slots=True)
class EvidenceItem:
    """单条证据

    Attributes:
        kind: 证据类型（tool/context）
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


class EvidenceComposer:
    """证据合成器

    收集多工具调用结果，按相关性排序，合成LLM可用的结构化证据文本。
    """

    def __init__(self) -> None:
        """初始化证据合成器"""
        self._items: list[EvidenceItem] = []

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

    def compose(self, max_items: int = 5) -> str:
        """合成证据文本

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
            lines.append(
                f"{i}. [{kind_label}|{item.source}] {content}"
            )
        return "\n".join(lines)

    def build_evidence_guidance(self) -> str:
        """构建证据使用指导提示

        返回:
            str: 证据指导文本
        """
        if not self._items:
            return ""
        tool_count = sum(
            1 for i in self._items if i.kind == EVIDENCE_KIND_TOOL
        )
        ctx_count = sum(
            1 for i in self._items if i.kind == EVIDENCE_KIND_CONTEXT
        )
        lines = [
            f"已收集 {tool_count} 条工具证据和 {ctx_count} 条上下文证据。",
            "请基于上述证据回复用户，注意：",
            "1. 优先使用相关性高的证据",
            "2. 不要暴露工具调用细节",
            "3. 用角色口吻自然表达",
        ]
        return "\n".join(lines)

    def clear(self) -> None:
        """清空证据"""
        self._items.clear()

    @property
    def items(self) -> list[EvidenceItem]:
        """获取所有证据项"""
        return list(self._items)
