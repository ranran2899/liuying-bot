"""Token消耗账本

对接 liuying.utils.LLM.token_tracker，按 group/user/purpose 维度
记录每次 LLM 调用的 prompt/completion tokens，提供统计查询接口。
数据持久化到数据库，重启后保留。

本模块还提供会话级用量累加器：通过 patch token_tracker.record，
在一次对话周期内累计所有 LLM 调用的 token 消耗，
供用户对话额度（UserToken）按实际消耗扣费使用。
"""

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from functools import wraps
from typing import Any, ClassVar

from liuying.utils.LLM import token_tracker
from liuying.utils.log import logger

from ...models.token_ledger_record import TokenLedgerRecord

# 上下文变量：当前调用上下文（group_id/user_id/purpose）
_current_context: ContextVar[dict[str, str] | None] = ContextVar(
    "ai_token_context", default=None
)
"""当前Token记录上下文"""

# 会话级用量累加器：当前对话周期内累计 token 消耗
_conversation_usage: ContextVar[dict[str, int] | None] = ContextVar(
    "ai_conversation_usage", default=None
)
"""当前对话的 token 用量累加器（None 表示未开启追踪）"""

# 标记是否已 patch 过 token_tracker.record
_tracker_patched: bool = False
"""token_tracker.record 是否已被 patch"""


class TokenTrackingHelper:
    """Token追踪辅助器

    封装会话级用量追踪与上下文管理的辅助方法，
    所有方法均为静态方法，可通过类名直接调用。
    """

    @staticmethod
    def _patch_token_tracker() -> None:
        """patch token_tracker.record 使其同时累计到会话级累加器

        patch 是幂等的，仅执行一次。patch 后所有 provider 调用
        token_tracker.record 时，若当前会话开启了追踪，则将
        prompt/completion/total tokens 累加到 ContextVar。
        """
        global _tracker_patched
        if _tracker_patched:
            return
        _tracker_patched = True

        original_record = token_tracker.record

        async def _patched_record(
            provider: str = "",
            model: str = "",
            prompt_tokens: int = 0,
            completion_tokens: int = 0,
            total_tokens: int = 0,
        ) -> None:
            """patched record：先调用原始记录，再累计到会话累加器"""
            try:
                await original_record(
                    provider=provider,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                )
            except Exception as e:
                logger.debug(
                    f"token_tracker 原始记录失败（不影响累加）: {e}",
                    command="AI",
                    e=e,
                )
            # 累计到会话级 ContextVar
            acc = _conversation_usage.get()
            if acc is None:
                return
            if total_tokens <= 0:
                total_tokens = prompt_tokens + completion_tokens
            acc["prompt_tokens"] += max(0, prompt_tokens)
            acc["completion_tokens"] += max(0, completion_tokens)
            acc["total_tokens"] += max(0, total_tokens)
            acc["call_count"] += 1

        token_tracker.record = _patched_record
        logger.debug(
            "token_tracker.record 已 patch，启用会话级用量追踪",
            command="AI",
        )

    @staticmethod
    def start_conversation_tracking() -> Any:
        """开启会话级 token 用量追踪

        初始化一个累加器字典并通过 ContextVar 绑定到当前异步上下文，
        在此上下文内发起的所有 LLM 调用都会累加到此字典。

        返回:
            Any: ContextVar token，用于结束后 reset 回原状态。
        """
        TokenTrackingHelper._patch_token_tracker()
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
        if accumulator is None:
            return {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "call_count": 0,
            }
        return accumulator

    @staticmethod
    def set_token_context(
        group_id: str = "",
        user_id: str = "",
        purpose: str = "chat",
    ) -> Any:
        """设置当前调用的Token上下文

        用于在LLM调用链路中传递 group/user/purpose 信息。

        参数:
            group_id: 群组ID
            user_id: 用户ID
            purpose: 调用用途

        返回:
            Token: contextvar token，用于reset
        """
        return _current_context.set(
            {"group_id": group_id, "user_id": user_id, "purpose": purpose}
        )

    @staticmethod
    def reset_token_context(token: Any) -> None:
        """重置Token上下文

        参数:
            token: set_token_context返回的token
        """
        _current_context.reset(token)

    @staticmethod
    def get_token_context() -> dict[str, str]:
        """获取当前Token上下文

        返回:
            dict: 含 group_id/user_id/purpose
        """
        return _current_context.get() or {}

    @staticmethod
    def with_token_tracking(
        purpose: str = "chat",
    ) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
        """Token追踪装饰器

        自动从上下文读取 group/user 信息，记录LLM调用的Token消耗。

        参数:
            purpose: 调用用途

        返回:
            装饰器函数
        """

        def decorator(
            func: Callable[..., Awaitable[Any]],
        ) -> Callable[..., Awaitable[Any]]:
            """装饰器内部实现"""

            @wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                """包装函数"""
                ctx = TokenTrackingHelper.get_token_context()
                result = await func(*args, **kwargs)
                # 仅从 dict 结果中提取 token 信息；
                # tuple（如 llm_helper.chat 返回的 (reasoning, content)）
                # 不含 usage 字段，直接跳过避免 AttributeError。
                if isinstance(result, dict):
                    usage = result.get("usage") or result.get("token_usage")
                    if usage and isinstance(usage, dict):
                        await TokenLedger.record(
                            provider=usage.get("provider", ""),
                            model=usage.get("model", ""),
                            prompt_tokens=usage.get("prompt_tokens", 0),
                            completion_tokens=usage.get("completion_tokens", 0),
                            total_tokens=usage.get("total_tokens", 0),
                            group_id=ctx.get("group_id", ""),
                            user_id=ctx.get("user_id", ""),
                            purpose=purpose,
                        )
                return result

            return wrapper

        return decorator


class TokenLedger:
    """Token账本管理器

    同步记录到数据库 + 内存追踪器，提供查询接口。
    """

    # 模型成本权重（每1K token的成本评分）
    _MODEL_COST_WEIGHTS: ClassVar[dict[str, float]] = {
        "gpt-4": 0.06,
        "gpt-4-turbo": 0.012,
        "gpt-3.5-turbo": 0.002,
        "glm-4": 0.015,
        "glm-4-flash": 0.001,
        "glm-4v": 0.05,
        "dall-e-3": 0.04,
        "tts-1": 0.015,
    }
    """模型成本权重表"""

    @classmethod
    def _calc_cost_score(
        cls, model: str, prompt_tokens: int, completion_tokens: int
    ) -> float:
        """计算成本评分

        参数:
            model: 模型名
            prompt_tokens: 提示Token数
            completion_tokens: 补全Token数

        返回:
            float: 成本评分
        """
        weight = cls._MODEL_COST_WEIGHTS.get(model, 0.005)
        return (prompt_tokens + completion_tokens) / 1000.0 * weight

    @classmethod
    async def record(
        cls,
        provider: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        group_id: str = "",
        user_id: str = "",
        purpose: str = "chat",
        extra: dict[str, Any] | None = None,
    ) -> None:
        """记录一次Token消耗

        同时写入数据库和内存追踪器。

        参数:
            provider: 供应商名
            model: 模型名
            prompt_tokens: 提示Token数
            completion_tokens: 补全Token数
            total_tokens: 总Token数（0时自动计算）
            group_id: 群组ID
            user_id: 用户ID
            purpose: 调用用途
            extra: 额外信息
        """
        if total_tokens <= 0:
            total_tokens = prompt_tokens + completion_tokens
        if total_tokens <= 0:
            return

        # 写入内存追踪器
        await token_tracker.record(
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

        # 写入数据库
        cost_score = cls._calc_cost_score(
            model, prompt_tokens, completion_tokens
        )
        try:
            await TokenLedgerRecord.add_record(
                provider=provider,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                group_id=group_id,
                user_id=user_id,
                purpose=purpose,
                cost_score=cost_score,
                extra=extra,
            )
        except Exception as e:
            logger.debug(
                f"Token账本记录写入失败（不影响主流程）: {e}",
                command="AI",
                e=e,
            )

    @classmethod
    async def record_from_context(
        cls,
        provider: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """从当前上下文记录Token消耗

        读取 contextvar 中的 group_id/user_id/purpose。

        参数:
            provider: 供应商名
            model: 模型名
            prompt_tokens: 提示Token数
            completion_tokens: 补全Token数
            total_tokens: 总Token数
            extra: 额外信息
        """
        ctx = get_token_context()
        await cls.record(
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            group_id=ctx.get("group_id", ""),
            user_id=ctx.get("user_id", ""),
            purpose=ctx.get("purpose", "chat"),
            extra=extra,
        )

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
    async def get_total(cls) -> dict[str, int]:
        """获取全局内存统计

        返回:
            dict: 全局统计（内存数据，重启清零）
        """
        return await token_tracker.get_total()

    @classmethod
    async def prune_old(cls, days: int = 90) -> int:
        """清理过期记录

        参数:
            days: 保留天数

        返回:
            int: 删除的记录数
        """
        return await TokenLedgerRecord.prune_old_records(days)


# 向后兼容别名：保持模块级函数可被直接导入
_patch_token_tracker = TokenTrackingHelper._patch_token_tracker
start_conversation_tracking = TokenTrackingHelper.start_conversation_tracking
stop_conversation_tracking = TokenTrackingHelper.stop_conversation_tracking
set_token_context = TokenTrackingHelper.set_token_context
reset_token_context = TokenTrackingHelper.reset_token_context
get_token_context = TokenTrackingHelper.get_token_context
with_token_tracking = TokenTrackingHelper.with_token_tracking

token_ledger = TokenLedger()
"""Token账本单例"""
