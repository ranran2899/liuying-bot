"""内容审核

独立内容审核模块，提供规则与 LLM 双层审核能力。
规则层快速命中明显违规关键词；LLM 层对模糊内容深度判断，
检测色情、暴力、政治等敏感内容。
"""

import json
import re
from typing import Any

from liuying.utils.log import logger

from ...config import get_config
from ..llm import llm_helper

__all__ = ["ContentModerator", "content_moderator"]


_QUICK_CHECK_MAX_LEN = 1000
"""快速检查最大文本长度"""


_PORNO_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:色情|淫秽|裸体|做爱|性交|黄色视频|av女优)", re.IGNORECASE),
    re.compile(r"\b(?:porn|nude|erotic|hardcore)\b", re.IGNORECASE),
)
"""色情类规则正则"""


_VIOLENCE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:杀人|自杀方法|炸弹制作|投毒|分尸|虐杀)"),
    re.compile(r"\b(?:how to kill|make bomb|poison)\b", re.IGNORECASE),
)
"""暴力类规则正则"""


_POLITICAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:颠覆国家|分裂国家|反动言论)"),
)
"""政治类规则正则"""


_CATEGORY_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "porn": _PORNO_PATTERNS,
    "violence": _VIOLENCE_PATTERNS,
    "political": _POLITICAL_PATTERNS,
}
"""类别到正则元组的映射"""


_MODERATE_PROMPT = """请审核以下文本是否包含敏感内容。
按JSON格式返回，字段：
- passed: 是否通过（true/false）
- issues: 问题数组，每项含 category（porn/violence/political/other）
  与 reason（简述）

文本：{text}
只返回JSON。"""
"""内容审核prompt"""


_PASSED_RESULT: dict[str, Any] = {
    "passed": True,
    "issues": [],
}
"""审核通过时的默认结果"""


class ContentModerator:
    """内容审核器

    提供两层审核：
    1. 规则层 quick_check 快速命中明显违规；
    2. LLM 层 moderate 对模糊内容深度判断。
    """

    def __init__(self) -> None:
        """初始化内容审核器"""

    def _is_enabled(self) -> bool:
        """检查内容审核是否启用

        返回:
            bool: 是否启用
        """
        return bool(get_config("CONTENT_MODERATION_ENABLED", True))

    def _rule_scan(self, text: str) -> list[dict[str, str]]:
        """规则层扫描敏感内容

        参数:
            text: 待扫描文本

        返回:
            list[dict]: 命中的问题列表，每项含 category/reason
        """
        if not text:
            return []
        sample = text[:_QUICK_CHECK_MAX_LEN]
        issues: list[dict[str, str]] = []
        for category, patterns in _CATEGORY_PATTERNS.items():
            for pattern in patterns:
                match = pattern.search(sample)
                if match:
                    issues.append(
                        {
                            "category": category,
                            "reason": f"规则命中: {match.group(0)}",
                        }
                    )
                    break
        return issues

    def quick_check(self, text: str) -> bool:
        """快速规则检查

        参数:
            text: 待检查文本

        返回:
            bool: True表示通过（未命中规则），False表示违规
        """
        if not self._is_enabled() or not text:
            return True
        issues = self._rule_scan(text)
        return not issues

    def _parse_moderate_response(
        self, response: str
    ) -> dict[str, Any]:
        """解析 LLM 审核响应

        参数:
            response: LLM响应文本

        返回:
            dict: 含 passed/issues 字段
        """
        if not response:
            return dict(_PASSED_RESULT)
        try:
            data = json.loads(response.strip())
        except (json.JSONDecodeError, ValueError) as e:
            logger.debug(
                f"审核响应解析失败: {e}",
                command="AI",
                e=e,
            )
            return dict(_PASSED_RESULT)

        if not isinstance(data, dict):
            return dict(_PASSED_RESULT)

        passed_raw = data.get("passed", True)
        passed = bool(passed_raw)
        issues_raw = data.get("issues", [])
        if isinstance(issues_raw, list):
            issues = [
                {
                    "category": str(i.get("category", "other")).strip(),
                    "reason": str(i.get("reason", "")).strip(),
                }
                for i in issues_raw
                if isinstance(i, dict)
            ]
        else:
            issues = []
        return {"passed": passed, "issues": issues}

    async def moderate(self, text: str) -> dict:
        """双层审核文本内容

        先做规则检查，命中则直接返回；未命中时调用 LLM 深度审核。

        参数:
            text: 待审核文本

        返回:
            dict: 含 passed/issues 字段
        """
        if not self._is_enabled() or not text:
            return dict(_PASSED_RESULT)

        rule_issues = self._rule_scan(text)
        if rule_issues:
            return {"passed": False, "issues": rule_issues}

        safe_text = text[:500]
        prompt = _MODERATE_PROMPT.format(text=safe_text)
        messages = [{"role": "user", "content": prompt}]

        try:
            response = await llm_helper.chat_text(
                messages,
                options={"temperature": 0.0},
            )
            return self._parse_moderate_response(response)
        except Exception as e:
            logger.warning(
                f"LLM审核失败，按通过处理: {e}",
                command="AI",
                e=e,
            )
            return dict(_PASSED_RESULT)


content_moderator = ContentModerator()
"""内容审核器单例"""
