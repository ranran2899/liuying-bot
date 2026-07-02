"""响应审查器

在Agent响应生成后、发送前对回复文本进行质量审查，
拦截AI味过重、格式化输出、模板化用语等问题。
"""

import json
import re

from liuying.utils.log import logger

from ...config import get_config
from ..llm import llm_helper

_AI_TONE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:总之|综上所述|总而言之|结语)[，,]?\s*"),
    re.compile(r"(?:希望|相信)(?:以上|这些)(?:内容|信息|回答).*?(?:帮助|有用)"),
    re.compile(r"(?:如果还有|若您有)(?:其他|更多)(?:问题|疑问).*?(?:随时|欢迎).*?(?:问|联系)"),
    re.compile(r"(?:以上是|上述就是).*?(?:回答|解答|分析|内容)"),
    re.compile(r"(?:感谢|谢谢)(?:您的?)?(?:提问|咨询|提问)"),
    re.compile(r"作为(?:一个|一名)?\s*(?:AI|人工智能|语言模型|助手|聊天机器人)"),
    re.compile(r"(?:我是|本人是)(?:一个|一名)?\s*(?:AI|人工智能|语言模型|助手)"),
    re.compile(r"(?:请问|请告诉我).*?(?:呢|吗|嘛)\s*[？?]?\s*$"),
)
"""AI味文本模式"""

_MARKDOWN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^#{1,6}\s+", re.MULTILINE),
    re.compile(r"^\s*[-*+]\s+", re.MULTILINE),
    re.compile(r"^\s*\d+\.\s+", re.MULTILINE),
    re.compile(r"\*\*[^*]+\*\*"),
    re.compile(r"__[^_]+__"),
    re.compile(r"`[^`]+`"),
    re.compile(r"```"),
)
"""Markdown格式模式"""

_REVIEW_PROMPT = """请审查以下AI回复是否存在问题。

用户消息：{user_msg}
AI回复：{reply}

审查标准（只返回JSON，不要其他内容）：
1. ai_tone: 回复是否有明显的AI助手语气
   （如"以上是..."、"综上所述..."、"作为AI..."等），true/false
2. markdown: 回复是否包含Markdown格式（标题、列表、加粗等），true/false
3. too_long: 回复是否过长（超过200字），true/false
4. off_topic: 回复是否偏离用户话题，true/false
5. hallucination: 回复是否可能包含虚构信息，true/false
6. suggestion: 如有问题，给出修改建议（简短），无问题返回空字符串

返回格式：{{"ai_tone": false, "markdown": false, "too_long": false,
"off_topic": false, "hallucination": false, "suggestion": ""}}"""

_MAX_REPLY_LEN = 200


class ReviewResult:
    """审查结果

    Attributes:
        passed: 是否通过审查
        issues: 问题标签列表
        suggestion: 修改建议
        cleaned_text: 清洗后的文本
    """

    __slots__ = ("cleaned_text", "issues", "passed", "suggestion")

    def __init__(
        self,
        passed: bool = True,
        issues: list[str] | None = None,
        suggestion: str = "",
        cleaned_text: str = "",
    ) -> None:
        """初始化审查结果

        参数:
            passed: 是否通过
            issues: 问题列表
            suggestion: 建议
            cleaned_text: 清洗后文本
        """
        self.passed = passed
        self.issues = issues or []
        self.suggestion = suggestion
        self.cleaned_text = cleaned_text

    def to_dict(self) -> dict:
        """转为字典"""
        return {
            "passed": self.passed,
            "issues": self.issues,
            "suggestion": self.suggestion,
        }


def _strip_markdown(text: str) -> str:
    """清除Markdown格式

    参数:
        text: 原始文本

    返回:
        str: 清洗后文本
    """
    result = text
    for pattern in _MARKDOWN_PATTERNS:
        result = pattern.sub("", result)
    return result.strip()


def _strip_ai_tone(text: str) -> str:
    """清除AI味尾缀

    参数:
        text: 原始文本

    返回:
        str: 清洗后文本
    """
    result = text
    for pattern in _AI_TONE_PATTERNS:
        result = pattern.sub("", result)
    return result.strip()


class ResponseReviewer:
    """响应审查器

    分两层审查：
    1. 正则快速扫描（零LLM成本）拦截明显问题
    2. LLM深度审查（可配置开关）检查语义问题
    """

    def __init__(self, llm=None) -> None:
        """初始化

        参数:
            llm: LLM助手实例，None时延迟获取
        """
        self._llm = llm

    def _get_llm(self):
        """延迟获取LLM助手"""
        if self._llm is None:
            self._llm = llm_helper
        return self._llm

    def quick_scan(self, reply: str, user_msg: str = "") -> ReviewResult:
        """正则快速扫描

        零LLM成本，检测AI味、Markdown、过长等明显问题。

        参数:
            reply: AI回复文本
            user_msg: 用户消息（用于上下文）

        返回:
            ReviewResult: 审查结果
        """
        issues: list[str] = []
        cleaned = reply

        has_md = any(p.search(reply) for p in _MARKDOWN_PATTERNS)
        if has_md:
            issues.append("markdown")
            cleaned = _strip_markdown(cleaned)

        has_ai_tone = any(p.search(reply) for p in _AI_TONE_PATTERNS)
        if has_ai_tone:
            issues.append("ai_tone")
            cleaned = _strip_ai_tone(cleaned)

        if len(reply) > _MAX_REPLY_LEN:
            issues.append("too_long")

        return ReviewResult(
            passed=len(issues) == 0,
            issues=issues,
            cleaned_text=cleaned,
        )

    async def deep_review(
        self,
        reply: str,
        user_msg: str = "",
        context: str = "",
    ) -> ReviewResult:
        """LLM深度审查

        在快速扫描基础上，调用LLM检查语义问题。

        参数:
            reply: AI回复文本
            user_msg: 用户消息
            context: 对话上下文

        返回:
            ReviewResult: 审查结果
        """
        quick = self.quick_scan(reply, user_msg)
        if not quick.passed:
            return quick

        try:
            prompt = _REVIEW_PROMPT.format(
                user_msg=user_msg[:200],
                reply=reply[:300],
            )
            _, raw = await self._get_llm().chat(
                [{"role": "user", "content": prompt}],
                options={"temperature": 0.1},
            )
            result = self._parse_review_json(raw)
            if result:
                issues = [
                    k
                    for k in (
                        "ai_tone",
                        "markdown",
                        "too_long",
                        "off_topic",
                        "hallucination",
                    )
                    if result.get(k) is True
                ]
                suggestion = result.get("suggestion", "")
                return ReviewResult(
                    passed=len(issues) == 0,
                    issues=issues,
                    suggestion=suggestion,
                    cleaned_text=reply,
                )
        except Exception as e:
            logger.debug(
                f"LLM深度审查失败，降级到快速扫描: {e}",
                command="AI",
                e=e,
            )
        return quick

    def _parse_review_json(self, raw: str) -> dict | None:
        """解析审查JSON

        参数:
            raw: LLM返回的原始文本

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

    async def review(
        self,
        reply: str,
        user_msg: str = "",
        context: str = "",
        use_llm: bool | None = None,
    ) -> ReviewResult:
        """审查入口

        参数:
            reply: AI回复文本
            user_msg: 用户消息
            context: 上下文
            use_llm: 是否使用LLM深度审查，None时用配置

        返回:
            ReviewResult: 审查结果
        """
        if not reply or not reply.strip():
            return ReviewResult(passed=True, cleaned_text=reply)

        should_llm = use_llm
        if should_llm is None:
            should_llm = get_config("RESPONSE_REVIEW_ENABLED", False)

        if should_llm:
            return await self.deep_review(reply, user_msg, context)
        return self.quick_scan(reply, user_msg)

    def clean_reply(self, reply: str) -> str:
        """清洗回复文本（快速）

        参数:
            reply: 原始回复

        返回:
            str: 清洗后文本
        """
        result = _strip_markdown(reply)
        result = _strip_ai_tone(result)
        return result.strip()


response_reviewer = ResponseReviewer()
"""响应审查器单例"""
