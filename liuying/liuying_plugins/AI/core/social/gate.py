"""社交智能门控

在主动社交场景决定 draft 之后，让 LLM 二次判断
"现在发这条合不合适"。避免bot显得唐突或在用户
不想被打扰时推送。

返回 (allow, rewritten, reason)：
- (False, None, reason) 拒绝发送
- (True, None, reason) 允许且不改文案
- (True, modified, reason) 允许但LLM改了文案
"""

from liuying.utils.log import logger

from ..json_utils import extract_json_payload
from ..llm import llm_helper

__all__ = ["SocialGate", "social_gate"]


class SocialGate:
    """社交智能门控

    封装 LLM 二次判断主动消息是否合适的逻辑。
    失败时默认 allow（不阻塞正常发送）。

    判断维度：
    - 当前时间是否打扰用户
    - 文案是否自然像真人主动
    - 文案是否与用户画像贴合
    - 是否会显得"为了发而发"
    """

    @staticmethod
    async def gate_should_send(
        *,
        scenario: str,
        user_id: str,
        draft: str,
        persona_snippet: str = "",
        now_str: str = "",
    ) -> tuple[bool, str | None, str]:
        """二次判断是否发送主动消息

        参数:
            scenario: 场景名称
            user_id: 用户ID
            draft: 初稿文案
            persona_snippet: 用户画像摘要
            now_str: 当前时间字符串

        返回:
            tuple[bool, str|None, str]: (是否允许, 改写文案或None, 原因)
        """
        prompt = (
            "你是一个主动社交闸门，负责判断 bot 是否应该在此刻主动联系用户。\n\n"
            "[本次想发的场景]\n"
            f"{scenario}\n\n"
            "[初稿文案]\n"
            f"{draft}\n\n"
            "[用户信息]\n"
            f"- user_id: {user_id}\n"
            f"- 用户画像摘要：{(persona_snippet or '<无>')[:200]}\n"
            f"- 当前时间：{now_str or ''}\n\n"
            "[判断维度]\n"
            "- 当前时间是否打扰用户（深夜/上班高峰等需谨慎）\n"
            "- 文案是否自然像真人主动，而不是模板化群发\n"
            "- 文案是否与用户画像/最近互动主题贴合\n"
            "- 是否会显得「为了发而发」\n\n"
            "[输出]\n"
            "严格输出 JSON：\n"
            "{{\n"
            '  "allow": true 或 false,\n'
            '  "reason": "一句话说明",\n'
            '  "rewritten": "如果需要小改，把改后的文案放这（不改就给空串）"\n'
            "}}"
        )
        try:
            text = await llm_helper.chat_text(
                [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                options={"temperature": 0.2},
            )
        except Exception as exc:
            logger.debug(
                f"社交门控LLM调用失败，默认允许: {exc}",
                command="AI",
                e=exc,
            )
            return True, None, f"gate llm failed: {exc}"

        text = str(text or "").strip()
        if not text:
            return True, None, "gate empty response"

        parsed = extract_json_payload(text)
        if parsed is None:
            return True, None, "gate non-json, default allow"

        allow = bool(parsed.get("allow", True))
        rewritten = (
            str(parsed.get("rewritten", "") or "").strip()
            or None
        )
        reason = str(
            parsed.get("reason", "") or ""
        ).strip()
        return allow, rewritten, reason


social_gate = SocialGate()
"""社交门控单例"""
