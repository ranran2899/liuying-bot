"""交叉验证器

在Agent工具调用结果与LLM响应之间进行事实交叉验证，
检测回复是否与工具证据矛盾或存在幻觉。
"""

import json
import re

from liuying.utils.log import logger

from ..llm import llm_helper

_VERIFY_PROMPT = """请验证AI回复是否与工具检索到的证据一致。

用户问题：{question}
工具证据：{evidence}
AI回复：{reply}

验证标准（只返回JSON）：
1. consistent: 回复是否与证据一致（无矛盾），true/false
2. hallucination: 回复是否包含证据中不存在的事实，true/false
3. contradiction: 回复是否与证据直接矛盾，true/false
4. issue: 问题描述（无问题返回空字符串）

返回格式：{{"consistent": true, "hallucination": false,
"contradiction": false, "issue": ""}}"""

_MAX_EVIDENCE_LEN = 800
"""证据文本最大长度"""

_MAX_REPLY_LEN = 400
"""回复文本最大长度"""


class CrossVerifier:
    """交叉验证器

    在Agent响应生成后，将回复与工具调用收集的证据进行交叉验证，
    检测幻觉和事实矛盾。
    """

    def __init__(self, llm=None) -> None:
        """初始化

        参数:
            llm: LLM助手实例
        """
        self._llm = llm

    def _get_llm(self):
        """延迟获取LLM助手"""
        if self._llm is None:
            self._llm = llm_helper
        return self._llm

    def _build_evidence_text(
        self, tool_records: list[dict]
    ) -> str:
        """从工具调用记录构建证据文本

        参数:
            tool_records: 工具调用记录列表

        返回:
            str: 证据文本
        """
        parts: list[str] = []
        for record in tool_records:
            if not record.get("success"):
                continue
            name = record.get("name", "unknown")
            result = str(record.get("result", ""))[:200]
            parts.append(f"[{name}] {result}")
        return "\n".join(parts)[:_MAX_EVIDENCE_LEN]

    async def verify(
        self,
        reply: str,
        question: str,
        tool_records: list[dict] | None = None,
    ) -> dict:
        """交叉验证回复与证据

        参数:
            reply: AI回复文本
            question: 用户原始问题
            tool_records: 工具调用记录

        返回:
            dict: 验证结果，含 consistent/hallucination/contradiction/issue
        """
        if not reply or not reply.strip():
            return {"consistent": True, "hallucination": False,
                    "contradiction": False, "issue": ""}

        evidence = self._build_evidence_text(tool_records or [])
        if not evidence:
            return {"consistent": True, "hallucination": False,
                    "contradiction": False, "issue": ""}

        try:
            prompt = _VERIFY_PROMPT.format(
                question=question[:200],
                evidence=evidence,
                reply=reply[:_MAX_REPLY_LEN],
            )
            _, raw = await self._get_llm().chat(
                [{"role": "user", "content": prompt}],
                options={"temperature": 0.1},
            )
            result = self._parse_verify_json(raw)
            if result:
                return result
        except Exception as e:
            logger.debug(
                f"交叉验证失败，跳过: {e}",
                command="AI",
                e=e,
            )
        return {"consistent": True, "hallucination": False,
                "contradiction": False, "issue": ""}

    def _parse_verify_json(self, raw: str) -> dict | None:
        """解析验证JSON

        参数:
            raw: LLM返回文本

        返回:
            dict | None: 解析结果
        """

        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            match = re.search(r"\{[^{}]+\}", text)
            if match:
                try:
                    return json.loads(match.group())
                except (json.JSONDecodeError, ValueError):
                    pass
            return None

    async def should_regenerate(self, verify_result: dict) -> bool:
        """判断是否需要重新生成

        参数:
            verify_result: verify()返回的结果

        返回:
            bool: 是否需要重新生成
        """
        return bool(
            verify_result.get("hallucination")
            or verify_result.get("contradiction")
            or not verify_result.get("consistent", True)
        )


cross_verifier = CrossVerifier()
"""交叉验证器单例"""
