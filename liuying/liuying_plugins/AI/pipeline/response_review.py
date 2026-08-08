"""LLM 响应深度审查

在 Agent 生成回复后，使用独立 LLM 调用对回复进行二次审核。
审核维度：事实准确性、内容安全、语气一致性、信息完整度。
审核结果：通过 / 需修正 / 拒绝。需修正时返回修正后文本，
拒绝时返回默认安全回复。
"""

from dataclasses import dataclass

from liuying.utils.log import logger

from ..config import get_config
from ..core.json_utils import extract_json_payload
from ..core.llm import llm_helper
from ..core.llm.model_router import ROLE_REVIEW, model_router

_DEFAULT_SAFE_REPLY = "抱歉，我暂时无法回答这个问题。"

_PERSONA_STYLE_FALLBACK = "友好、自然的对话风格"


@dataclass(slots=True)
class ReviewResult:
    """审查结果

    Attributes:
        verdict: 审查结论（pass/fix/reject）
        reason: 原因简述
        final_text: 最终使用的回复文本
        reviewed: 是否实际执行了审查
    """

    verdict: str
    reason: str
    final_text: str
    reviewed: bool


class ResponseReviewer:
    """响应审查器

    对 LLM 生成的回复进行二次审核，确保回复质量与安全。
    受 RESPONSE_REVIEW_ENABLED 配置开关控制。
    """

    def __init__(self) -> None:
        """初始化响应审查器"""

    async def review(
        self,
        user_message: str,
        reply_text: str,
        persona_style: str = _PERSONA_STYLE_FALLBACK,
    ) -> ReviewResult:
        """审查回复文本

        参数:
            user_message: 用户原始消息
            reply_text: AI生成的回复文本
            persona_style: 人设风格描述

        返回:
            ReviewResult: 审查结果
        """
        if not get_config("RESPONSE_REVIEW_ENABLED", False):
            return ReviewResult(
                verdict="pass",
                reason="审查未启用",
                final_text=reply_text,
                reviewed=False,
            )
        if not reply_text or not reply_text.strip():
            return ReviewResult(
                verdict="pass",
                reason="空回复跳过审查",
                final_text=reply_text,
                reviewed=False,
            )
        try:
            prompt = (
                "你是一个回复审查助手。请审核以下AI回复是否适合发送给用户。\n"
                "\n"
                f"用户原始消息：{user_message[:200]}\n"
                f"AI生成的回复：{reply_text[:500]}\n"
                f"人设风格：{persona_style}\n"
                "\n"
                "审核维度：\n"
                "1. 事实准确性：回复中陈述的事实是否可信\n"
                "2. 内容安全：是否包含不当/有害/敏感内容\n"
                "3. 语气一致性：是否符合人设风格\n"
                "4. 信息完整度：是否完整回答了用户问题\n"
                "\n"
                "请输出JSON格式（只输出JSON，不要其他内容）：\n"
                "{{\n"
                '  "verdict": "pass|fix|reject",\n'
                '  "reason": "原因简述",\n'
                '  "fixed_text": "修正后的文本（verdict=fix时提供）"\n'
                "}}\n"
                "\n"
                "- pass: 回复合适，可直接发送\n"
                "- fix: 回复有小问题，提供修正版本\n"
                "- reject: 回复严重不当，需用默认回复替代"
            )
            role = model_router.resolve(ROLE_REVIEW)
            _, content = await llm_helper.chat(
                [{"role": "user", "content": prompt}],
                model=role.model or None,
                options=role.apply_to_options(),
                provider_name=role.provider or None,
            )
            return self._parse_review_result(
                content, reply_text
            )
        except Exception as e:
            logger.warning(
                f"响应审查失败，放行原回复: {e}",
                command="AI",
                e=e,
            )
            return ReviewResult(
                verdict="pass",
                reason=f"审查异常: {e}",
                final_text=reply_text,
                reviewed=False,
            )

    @staticmethod
    def _parse_review_result(
        raw: str, original: str
    ) -> ReviewResult:
        """解析 LLM 审查结果

        参数:
            raw: LLM 返回的原始文本
            original: 原始回复文本（兜底）

        返回:
            ReviewResult: 审查结果
        """
        data = extract_json_payload(raw)
        if data is None:
            logger.debug(
                f"审查结果解析失败，放行原回复: {raw[:100]}",
                command="AI",
            )
            return ReviewResult(
                verdict="pass",
                reason="解析失败放行",
                final_text=original,
                reviewed=True,
            )
        verdict = str(data.get("verdict", "pass")).lower()
        reason = str(data.get("reason", ""))
        match verdict:
            case "pass":
                return ReviewResult(
                    verdict="pass",
                    reason=reason,
                    final_text=original,
                    reviewed=True,
                )
            case "fix":
                fixed = str(data.get("fixed_text", "")).strip()
                return ReviewResult(
                    verdict="fix",
                    reason=reason,
                    final_text=fixed or original,
                    reviewed=True,
                )
            case "reject":
                logger.warning(
                    f"回复被审查拒绝: {reason}",
                    command="AI",
                )
                return ReviewResult(
                    verdict="reject",
                    reason=reason,
                    final_text=_DEFAULT_SAFE_REPLY,
                    reviewed=True,
                )
            case _:
                return ReviewResult(
                    verdict="pass",
                    reason=f"未知结论{verdict}放行",
                    final_text=original,
                    reviewed=True,
                )


response_reviewer = ResponseReviewer()
"""响应审查器单例"""
