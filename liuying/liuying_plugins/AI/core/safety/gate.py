"""社交LLM闸门

发送前用LLM二次决策"现在合不合适发消息"。
检查当前上下文是否适合主动发言，LLM失败时降级到规则模式。
"""

import json

from liuying.utils.log import logger

from ..llm import llm_helper

__all__ = ["SocialGate", "social_gate"]


_GATE_PROMPT = """请快速判断现在是否合适在群聊中主动发送消息。

待发送消息: {message}
群上下文: {context}
群ID: {group_id}

判断标准:
- 不打断正在进行的热烈讨论
- 不重复发送相似内容
- 内容与群氛围相符
- 深夜时段应保守

只返回JSON: {{"should_send": true/false}}"""


_GATE_SYSTEM_PROMPT = (
    "你是消息发送时机判断助手，只返回JSON。"
)
"""闸门系统提示词"""


class SocialGate:
    """社交LLM闸门

    发送前用LLM快速决策是否合适发消息。
    LLM连续失败超过阈值后降级到规则模式。
    """

    _FAILURE_THRESHOLD: int = 3
    """连续失败阈值，超过后降级到规则模式"""

    _MAX_MESSAGE_LEN: int = 200
    """LLM判断时截断的消息长度"""

    _MAX_CONTEXT_LEN: int = 500
    """LLM判断时截断的上下文长度"""

    def __init__(self) -> None:
        """初始化社交闸门"""
        self._failure_count: int = 0
        """连续失败计数"""

    async def should_send(
        self,
        user_msg: str,
        context: str,
        group_id: str,
    ) -> bool:
        """判断是否合适发送消息

        参数:
            user_msg: 待发送消息
            context: 当前上下文
            group_id: 群组ID

        返回:
            bool: 是否合适发送
        """
        if not user_msg:
            return False

        if self._failure_count >= self._FAILURE_THRESHOLD:
            return self._rule_based_check(
                user_msg, context, group_id
            )

        try:
            return await self._llm_check(
                user_msg, context, group_id
            )
        except Exception as e:
            self._failure_count += 1
            logger.debug(
                f"社交闸门LLM决策失败，降级规则模式: {e}",
                command="AI",
                e=e,
            )
            return self._rule_based_check(
                user_msg, context, group_id
            )

    async def _llm_check(
        self,
        user_msg: str,
        context: str,
        group_id: str,
    ) -> bool:
        """LLM决策是否合适发送

        参数:
            user_msg: 待发送消息
            context: 当前上下文
            group_id: 群组ID

        返回:
            bool: 是否合适发送

        异常:
            Exception: LLM调用失败
        """
        prompt = _GATE_PROMPT.format(
            message=user_msg[: self._MAX_MESSAGE_LEN],
            context=(
                context[: self._MAX_CONTEXT_LEN]
                if context
                else "无"
            ),
            group_id=group_id,
        )
        messages = [
            {"role": "system", "content": _GATE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        response = await llm_helper.chat_text(messages)
        self._failure_count = 0
        return self._parse_llm_response(response)

    def _parse_llm_response(self, response: str) -> bool:
        """解析LLM返回的JSON决策

        参数:
            response: LLM返回文本

        返回:
            bool: 是否发送
        """
        try:
            data = json.loads(response.strip())
            return bool(data.get("should_send", False))
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.debug(
                f"社交闸门LLM返回解析失败: {e}",
                command="AI",
                e=e,
            )
            return False

    def _rule_based_check(
        self,
        user_msg: str,
        context: str,
        group_id: str,
    ) -> bool:
        """规则模式判断是否合适发送

        参数:
            user_msg: 待发送消息
            context: 当前上下文
            group_id: 群组ID

        返回:
            bool: 是否合适发送
        """
        if not user_msg or len(user_msg) > 500:
            return False
        if context and user_msg in context:
            return False
        return True


social_gate = SocialGate()
"""社交闸门单例"""
