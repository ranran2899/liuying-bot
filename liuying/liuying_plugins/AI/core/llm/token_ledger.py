"""Token消耗账本

会话级用量追踪：通过本体 token_tracker 的 add_listener 官方回调，
在一次对话周期内累计所有 LLM 调用的 token 消耗，
供用户对话额度（UserToken）按实际消耗扣费使用。

数据持久化查询对接 TokenLedgerRecord 表。
"""

from contextvars import ContextVar
from typing import Any

from liuying.services.LLM import token_tracker

from ...models.token_ledger_record import TokenLedgerRecord

# 会话级用量累加器：当前对话周期内累计 token 消耗
_conversation_usage: ContextVar[dict[str, int] | None] = ContextVar(
    "ai_conversation_usage", default=None
)
"""当前对话的 token 用量累加器（None 表示未开启追踪）"""


def _on_token_record(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
) -> None:
    """本体 token_tracker 监听回调：累加到会话级累加器

    仅在当前异步上下文开启了追踪时生效；参数已在上游
    归一（total_tokens 非正时由调用方自行计算）。

    参数:
        provider: 供应商名
        model: 模型名
        prompt_tokens: 提示 token 数
        completion_tokens: 补全 token 数
        total_tokens: 总 token 数
    """
    acc = _conversation_usage.get()
    if acc is None:
        return
    if total_tokens <= 0:
        total_tokens = prompt_tokens + completion_tokens
    acc["prompt_tokens"] += max(0, prompt_tokens)
    acc["completion_tokens"] += max(0, completion_tokens)
    acc["total_tokens"] += max(0, total_tokens)
    acc["call_count"] += 1


_EMPTY_USAGE: dict[str, int] = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "call_count": 0,
}
"""未开启追踪时的空用量"""


class TokenTrackingHelper:
    """Token追踪辅助器

    会话级用量追踪的开关入口，供对话流水线在单次回复
    周期内统计全部 LLM 调用消耗。
    """

    @staticmethod
    def start_conversation_tracking() -> Any:
        """开启会话级 token 用量追踪

        向本体 token_tracker 注册监听回调（内部去重，幂等），
        初始化累加器字典并通过 ContextVar 绑定到当前异步上下文，
        在此上下文内发起的所有 LLM 调用都会累加到此字典。

        返回:
            Any: ContextVar token，用于结束后 reset 回原状态。
        """
        token_tracker.add_listener(_on_token_record)
        accumulator: dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "call_count": 0,
        }
        return _conversation_usage.set(accumulator)

    @staticmethod
    def stop_conversation_tracking(token: Any) -> dict[str, int]:
        """停止会话级追踪并返回累计用量

        参数:
            token: start_conversation_tracking 返回的 ContextVar token

        返回:
            dict: 累计用量，含 prompt_tokens/completion_tokens/
                total_tokens/call_count
        """
        accumulator = _conversation_usage.get()
        _conversation_usage.reset(token)
        return accumulator if accumulator is not None else _EMPTY_USAGE


class TokenLedger:
    """Token账本查询接口（只读）"""

    @classmethod
    async def get_summary(
        cls,
        group_id: str = "",
        user_id: str = "",
        purpose: str = "",
        hours: int = 24,
    ) -> dict[str, Any]:
        """获取Token消耗摘要

        参数:
            group_id: 群组ID
            user_id: 用户ID
            purpose: 调用用途
            hours: 统计时间窗口（小时）

        返回:
            dict: 摘要字典
        """
        return await TokenLedgerRecord.get_summary(
            group_id=group_id,
            user_id=user_id,
            purpose=purpose,
            hours=hours,
        )

    @classmethod
    async def prune_old(cls, days: int = 90) -> int:
        """清理过期记录

        参数:
            days: 保留天数

        返回:
            int: 删除的记录数
        """
        return await TokenLedgerRecord.prune_old_records(days)


token_ledger = TokenLedger()
"""Token账本单例"""
