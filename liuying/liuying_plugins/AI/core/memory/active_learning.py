"""主动学习引擎

基于不确定性检测的事实查证学习机制。
当LLM回复中包含不确定表述（"可能"、"大概"、"不确定"等），
且涉及事实性问题时，自主发起联网查证并将结果写入记忆。
"""

from datetime import date
import json
import re

from liuying.utils.log import logger

from ...config import get_config
from ..llm import llm_helper
from .manager import memory_manager

_UNCERTAIN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:可能|大概|也许|或许|应该|似乎|好像|不确定|不太清楚|大概)"),
    re.compile(r"(?:我不太确定|不太确定|记不清了|可能记错)"),
    re.compile(r"(?:好像是|应该是|大概是|也许是)"),
    re.compile(r"\?(?:\?+|！+)"),
)
"""不确定性表述模式"""

_FACTUAL_HINTS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:什么时候|哪一年|几点|日期|时间)"),
    re.compile(r"(?:多少人|多少个|数量|数目)"),
    re.compile(r"(?:在哪|哪里|什么地方|地址|位置)"),
    re.compile(r"(?:是谁|叫什么|名字|名称)"),
    re.compile(r"(?:是什么|什么意思|定义|含义)"),
    re.compile(r"(?:为什么|原因|为什么|为何)"),
)
"""事实性问题提示模式"""

_VERIFY_PROMPT = """请验证以下信息的准确性，并给出正确答案。

问题：{question}
待验证信息：{claim}

要求：
1. 判断信息是否准确
2. 如不准确，给出正确答案
3. 只返回JSON：{{"accurate": true/false,
   "correct": "正确答案或空字符串",
   "confidence": 0.0-1.0}}"""

_MAX_DAILY_QUOTA = 20
"""每日查证配额"""

_MAX_CLAIM_LEN = 200
"""待验证信息最大长度"""


class ActiveLearner:
    """主动学习引擎

    检测回复中的不确定性表述，对事实性问题发起查证，
    将正确信息写入记忆系统。
    """

    def __init__(self, llm=None) -> None:
        """初始化

        参数:
            llm: LLM助手实例
        """
        self._llm = llm
        self._daily_count = 0
        self._quota_reset_day = 0

    def _get_llm(self):
        """延迟获取LLM助手"""
        if self._llm is None:
            self._llm = llm_helper
        return self._llm

    def _reset_quota_if_needed(self) -> None:
        """按天重置配额"""
        today = date.today().toordinal()
        if today != self._quota_reset_day:
            self._daily_count = 0
            self._quota_reset_day = today

    def detect_uncertainty(self, reply: str) -> bool:
        """检测回复是否包含不确定性表述

        参数:
            reply: AI回复文本

        返回:
            bool: 是否包含不确定性
        """
        if not reply:
            return False
        return any(p.search(reply) for p in _UNCERTAIN_PATTERNS)

    def is_factual_question(self, question: str) -> bool:
        """判断是否为事实性问题

        参数:
            question: 用户问题

        返回:
            bool: 是否为事实性问题
        """
        if not question:
            return False
        return any(p.search(question) for p in _FACTUAL_HINTS)

    def should_learn(
        self,
        question: str,
        reply: str,
    ) -> bool:
        """判断是否需要触发主动学习

        参数:
            question: 用户问题
            reply: AI回复

        返回:
            bool: 是否触发
        """
        if not get_config("ACTIVE_LEARNING_ENABLED", False):
            return False
        self._reset_quota_if_needed()
        if self._daily_count >= _MAX_DAILY_QUOTA:
            return False
        if not self.is_factual_question(question):
            return False
        return self.detect_uncertainty(reply)

    async def learn(
        self,
        question: str,
        claim: str,
        user_id: str = "",
        group_id: str | None = None,
    ) -> dict | None:
        """执行主动学习

        参数:
            question: 用户问题
            claim: 待验证的信息
            user_id: 用户ID
            group_id: 群组ID

        返回:
            dict | None: 学习结果，含 accurate/correct/confidence
        """
        self._reset_quota_if_needed()
        if self._daily_count >= _MAX_DAILY_QUOTA:
            return None

        try:
            verify_result = await self._verify_claim(question, claim)
            if verify_result and not verify_result.get("accurate", True):
                correct = verify_result.get("correct", "")
                if correct:
                    await memory_manager.add(
                        user_id=user_id or "system",
                        content=f"Q: {question}\nA: {correct}",
                        summary=f"事实纠正: {question[:50]}",
                        group_id=group_id,
                        tier="semantic",
                        salience=0.9,
                        topic_tags=["fact_correction"],
                    )
                    logger.info(
                        f"主动学习: 纠正事实 '{question[:30]}'",
                        command="AI",
                    )
            self._daily_count += 1
            return verify_result
        except Exception as e:
            logger.debug(
                f"主动学习失败: {e}",
                command="AI",
                e=e,
            )
            return None

    async def _verify_claim(
        self,
        question: str,
        claim: str,
    ) -> dict | None:
        """验证信息准确性

        参数:
            question: 问题
            claim: 待验证信息

        返回:
            dict | None: 验证结果
        """

        prompt = _VERIFY_PROMPT.format(
            question=question[:200],
            claim=claim[:_MAX_CLAIM_LEN],
        )
        try:
            results = await self._get_llm().web_search(question, count=3)
            if results:
                evidence = "\n".join(
                    f"- {r.get('snippet', '')[:100]}"
                    for r in results[:3]
                )
                prompt = f"{prompt}\n\n网络证据：\n{evidence}"
        except Exception:
            pass

        _, raw = await self._get_llm().chat(
            [{"role": "user", "content": prompt}],
            options={"temperature": 0.1},
        )
        return self._parse_json(raw)

    def _parse_json(self, raw: str) -> dict | None:
        """解析JSON响应

        参数:
            raw: 原始文本

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

    async def maybe_learn(
        self,
        question: str,
        reply: str,
        user_id: str = "",
        group_id: str | None = None,
    ) -> dict | None:
        """条件触发主动学习

        自动判断是否需要学习，若需要则执行。

        参数:
            question: 用户问题
            reply: AI回复
            user_id: 用户ID
            group_id: 群组ID

        返回:
            dict | None: 学习结果或None
        """
        if not self.should_learn(question, reply):
            return None
        return await self.learn(
            question=question,
            claim=reply[:_MAX_CLAIM_LEN],
            user_id=user_id,
            group_id=group_id,
        )


active_learner = ActiveLearner()
"""主动学习器单例"""
