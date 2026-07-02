"""网页内容关联验证

将AI回复中的陈述与网络搜索结果关联，验证陈述可信度。
"""

import json
import re
from typing import Any

from liuying.utils.log import logger

from ..llm import llm_helper
from .search_ranker import search_ranker

_MAX_STATEMENTS = 5
"""最大提取陈述数"""

_MAX_STATEMENT_LEN = 200
"""单条陈述最大长度"""

_GROUNDING_PROMPT = (
    "请判断以下陈述是否被提供的搜索证据支持。\n"
    '输出JSON：{"supported": bool, "confidence": float, '
    '"reason": str}。\n'
    "confidence范围0.0-1.0。\n"
    "只输出JSON，不要解释。\n\n"
)
"""关联验证prompt前缀"""

_STATEMENT_SPLIT_RE = re.compile(
    r"[。！？\n；;]+"
)
"""陈述分隔正则"""


class WebGrounding:
    """网页内容关联验证器

    将回复陈述与搜索结果关联，输出验证报告。
    """

    async def ground(
        self, text: str, query: str
    ) -> dict[str, Any]:
        """文本与网络内容关联验证

        提取文本中的陈述，搜索证据并验证支持度。

        参数:
            text: 待验证文本
            query: 验证主题/查询

        返回:
            dict: 验证报告，含 supported/confidence/statements/evidence
        """
        if not text or not text.strip():
            return {
                "supported": False,
                "confidence": 0.0,
                "statements": [],
                "evidence": [],
                "reason": "空文本",
            }

        statements = self._extract_statements(text)
        if not statements:
            return {
                "supported": False,
                "confidence": 0.0,
                "statements": [],
                "evidence": [],
                "reason": "无可提取陈述",
            }

        try:
            evidence = await self._gather_evidence(query)
        except Exception as e:
            logger.debug(
                f"采集证据失败: {e}", command="AI", e=e
            )
            evidence = []

        verification = await self._verify_statements(
            statements, evidence, query
        )
        return verification

    def _extract_statements(self, text: str) -> list[str]:
        """从文本提取陈述

        参数:
            text: 原始文本

        返回:
            list[str]: 陈述列表
        """
        parts = _STATEMENT_SPLIT_RE.split(text)
        statements: list[str] = []
        for part in parts:
            cleaned = part.strip()
            if not cleaned or len(cleaned) < 6:
                continue
            if len(cleaned) > _MAX_STATEMENT_LEN:
                cleaned = cleaned[:_MAX_STATEMENT_LEN]
            statements.append(cleaned)
            if len(statements) >= _MAX_STATEMENTS:
                break
        return statements

    async def _gather_evidence(
        self, query: str
    ) -> list[dict[str, str]]:
        """采集搜索证据

        通过 llm_helper.web_search 调用统一 WebSearchCapability，
        由 liuying/plugins/web_search 插件提供免配置降级兜底。

        参数:
            query: 查询文本

        返回:
            list[dict]: 排序后的证据列表
        """
        results = await llm_helper.web_search(query, count=5)
        if not results:
            return []
        return search_ranker.rank(results, query)

    async def _verify_statements(
        self,
        statements: list[str],
        evidence: list[dict[str, str]],
        query: str,
    ) -> dict[str, Any]:
        """调用LLM验证陈述

        参数:
            statements: 陈述列表
            evidence: 证据列表
            query: 原始查询

        返回:
            dict: 验证报告
        """
        evidence_text = self._format_evidence(evidence)
        statements_text = "\n".join(
            f"{i + 1}. {s}" for i, s in enumerate(statements)
        )
        prompt = (
            f"{_GROUNDING_PROMPT}"
            f"主题: {query}\n"
            f"陈述:\n{statements_text}\n\n"
            f"搜索证据:\n{evidence_text}"
        )
        messages = [
            {
                "role": "system",
                "content": "你是事实核查助手，输出纯JSON。",
            },
            {"role": "user", "content": prompt},
        ]
        try:
            result = await llm_helper.chat_text(messages)
            return self._parse_verification(
                result, statements, evidence
            )
        except Exception as e:
            logger.warning(
                f"关联验证LLM调用失败: {e}",
                command="AI",
                e=e,
            )
            return {
                "supported": False,
                "confidence": 0.0,
                "statements": statements,
                "evidence": evidence,
                "reason": f"验证失败: {e}",
            }

    def _format_evidence(
        self, evidence: list[dict[str, str]]
    ) -> str:
        """格式化证据文本

        参数:
            evidence: 证据列表

        返回:
            str: 格式化文本
        """
        if not evidence:
            return "（无证据）"
        lines: list[str] = []
        for i, item in enumerate(evidence, 1):
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            url = item.get("url", "")
            lines.append(
                f"{i}. {title}\n   {snippet}\n   {url}"
            )
        return "\n".join(lines)

    def _parse_verification(
        self,
        result: str,
        statements: list[str],
        evidence: list[dict[str, str]],
    ) -> dict[str, Any]:
        """解析LLM验证结果

        参数:
            result: LLM返回文本
            statements: 陈述列表
            evidence: 证据列表

        返回:
            dict: 验证报告
        """
        text = (result or "").strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(text[start:end])
                except json.JSONDecodeError:
                    data = {}
            else:
                data = {}
        return {
            "supported": bool(data.get("supported", False)),
            "confidence": float(
                data.get("confidence", 0.0) or 0.0
            ),
            "statements": statements,
            "evidence": evidence,
            "reason": str(data.get("reason", "")),
        }


web_grounding = WebGrounding()
"""网页内容关联验证器单例"""
